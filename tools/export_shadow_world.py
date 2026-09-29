"""Bake static, camera-independent shadow geometry from a saved Minecraft 26.3 world.

Examples:
  python tools/export_shadow_world.py --world PATH --output PATH
  python tools/export_shadow_world.py --fixture boxes.json --output PATH
  python tools/export_shadow_world.py --check

Bounds are world coordinates, maximum exclusive. Fixture JSON is {"boxes":
[{"min":[0,0,0], "max":[8,1,8]}]}; six-number boxes are accepted too.
The exporter only reads worlds. Save/close the world first for a consistent snapshot.
Runtime uses the PNGs alone; Python/Java are export tools, not game dependencies.
"""
from __future__ import annotations

import argparse
from collections import Counter
import gzip
import io
import json
import math
import os
from pathlib import Path
import re
import struct
import subprocess
import tempfile
import zlib

import nbtlib
import numpy as np
from PIL import Image

CPB = 4
AIR = {"minecraft:air", "minecraft:cave_air", "minecraft:void_air"}
MAX_VOXELS = 128 * 1024 * 1024
MAX_TEXTURE = 8192

# The exact installed game provides its block-state occlusion shapes. No world or
# renderer is started, and no guessed full-cube substitute is used for stairs.
SHAPE_JAVA = r'''
import com.google.gson.*;
import java.nio.file.*;
import net.minecraft.SharedConstants;
import net.minecraft.server.Bootstrap;
import net.minecraft.core.BlockPos;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.resources.Identifier;
import net.minecraft.world.level.EmptyBlockGetter;
import net.minecraft.world.level.block.*;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.properties.Property;
import net.minecraft.world.phys.shapes.*;

public class ExportChromaShapes {
    @SuppressWarnings({"rawtypes", "unchecked"})
    static BlockState property(BlockState state, String name, String value) {
        Property p = state.getBlock().getStateDefinition().getProperty(name);
        if (p == null) throw new IllegalArgumentException("Unknown property " + name);
        return state.setValue(p, (Comparable)p.getValue(value).orElseThrow());
    }
    public static void main(String[] args) throws Exception {
        SharedConstants.tryDetectVersion(); Bootstrap.bootStrap();
        var input = JsonParser.parseString(Files.readString(Path.of(args[0]))).getAsJsonArray();
        var result = new JsonArray();
        for (var entry : input) {
            var record = new JsonObject(); var boxes = new JsonArray();
            try {
                var item = entry.getAsJsonObject();
                var id = Identifier.parse(item.get("name").getAsString());
                var block = BuiltInRegistries.BLOCK.getOptional(id).orElseThrow();
                BlockState state = block.defaultBlockState();
                for (var p : item.getAsJsonObject("properties").entrySet())
                    state = property(state, p.getKey(), p.getValue().getAsString());
                record.addProperty("canOcclude", state.canOcclude());
                record.addProperty("lightDampening", state.getLightDampening());
                record.addProperty("renderShape", state.getRenderShape().toString());
                boolean excluded = block instanceof HalfTransparentBlock
                    || block instanceof StainedGlassPaneBlock || block == Blocks.GLASS_PANE
                    || block instanceof LeavesBlock || block instanceof LiquidBlock;
                if (!state.isAir() && state.getRenderShape() == RenderShape.MODEL && !excluded) {
                    boolean collision = !state.canOcclude() || block instanceof FenceGateBlock;
                    var shape = state.canOcclude() ? state.getOcclusionShape() : Shapes.empty();
                    record.addProperty("collisionApproximation", collision);
                    // ponytail: collision fallback models an opaque body within its
                    // owning block; visual holes and protruding gate panels need model voxelization.
                    if (collision) shape = Shapes.or(shape, Shapes.join(
                        state.getCollisionShape(EmptyBlockGetter.INSTANCE, BlockPos.ZERO),
                        Shapes.block(), BooleanOp.AND));
                    for (var box : shape.toAabbs()) {
                        var b = new JsonArray();
                        for (double n : new double[]{box.minX,box.minY,box.minZ,box.maxX,box.maxY,box.maxZ}) b.add(n);
                        boxes.add(b);
                    }
                }
            } catch (Exception e) { record.addProperty("unsupported", e.toString()); }
            record.add("boxes", boxes); result.add(record);
        }
        Files.writeString(Path.of(args[1]), new Gson().toJson(result));
    }
}
'''


def state_key(entry):
    """26.3 accepts a string, {id,properties}, or the compact {'':id} form."""
    if isinstance(entry, str):
        return str(entry), ()
    name = entry.get("id", entry.get("Name", entry.get("")))
    if name is None:
        raise ValueError(f"Unknown block-state palette entry: {entry!r}")
    props = entry.get("properties", entry.get("Properties", {}))
    return str(name), tuple(sorted((str(k), str(v)) for k, v in props.items()))


def state_label(key):
    name, props = key
    return name + ("[" + ",".join(f"{k}={v}" for k, v in props) + "]" if props else "")


def decode_indices(data, palette_size):
    if palette_size == 1:
        return np.zeros(4096, dtype=np.uint16)
    bits = max(4, (palette_size - 1).bit_length())
    per_word = 64 // bits
    words = np.asarray(data, dtype=np.int64).view(np.uint64)
    if len(words) != (4096 + per_word - 1) // per_word:
        raise ValueError(f"Invalid palette storage: {len(words)} words for {palette_size} states")
    i = np.arange(4096, dtype=np.uint64)
    result = ((words[i // per_word] >> ((i % per_word) * bits)) & ((1 << bits) - 1)).astype(np.uint16)
    if result.max() >= palette_size:
        raise ValueError("Chunk refers to a missing block-state palette entry")
    return result


def decompress_chunk(payload, kind):
    if kind == 1:
        result = gzip.decompress(payload)
    elif kind == 2:
        result = zlib.decompress(payload)
    elif kind == 3:
        result = payload
    else:
        raise ValueError(f"Unsupported MCA compression {kind}; re-save using standard zlib first")
    if len(result) > 32 * 1024 * 1024:
        raise ValueError("Chunk exceeds 32 MiB decoded safety limit")
    return result


def read_sections(world, dimension, bounds):
    if not re.fullmatch(r"[a-z0-9_.-]+:[a-z0-9_./-]+", dimension):
        raise ValueError("Invalid dimension identifier")
    namespace, name = dimension.split(":", 1)
    if any(p in ("", ".", "..") for p in [namespace, *name.split("/")]):
        raise ValueError("Invalid dimension identifier")
    region = world / "dimensions" / namespace / name / "region"
    if not region.is_dir():
        legacy = {"minecraft:overworld": world / "region", "minecraft:the_nether": world / "DIM-1/region", "minecraft:the_end": world / "DIM1/region"}
        region = legacy.get(dimension, region)
    files = sorted(region.glob("r.*.*.mca"))
    if not files:
        raise ValueError(f"No region files in {region}")
    states, ids, sections, chunks = [], {}, [], 0
    for path in files:
        _, rx, rz, _ = path.name.split(".")
        with path.open("rb") as stream:
            header = stream.read(4096)
            if len(header) != 4096:
                raise ValueError(f"Truncated region header: {path}")
            for index in range(1024):
                offset = int.from_bytes(header[index * 4:index * 4 + 3], "big")
                sectors = header[index * 4 + 3]
                if offset == 0:
                    continue
                cx, cz = int(rx) * 32 + index % 32, int(rz) * 32 + index // 32
                if bounds is not None and (cx * 16 >= bounds[1][0] or (cx + 1) * 16 <= bounds[0][0] or cz * 16 >= bounds[1][2] or (cz + 1) * 16 <= bounds[0][2]):
                    continue
                if offset < 2 or sectors == 0:
                    raise ValueError(f"Invalid region location: {path}, chunk {index}")
                stream.seek(offset * 4096)
                record = stream.read(5)
                if len(record) != 5:
                    raise ValueError(f"Truncated chunk header: {path}, chunk {index}")
                length, kind = struct.unpack(">IB", record)
                if length < 1 or length > sectors * 4096 - 4:
                    raise ValueError(f"Invalid chunk length: {path}, chunk {index}")
                if kind & 128:
                    payload = (region / f"c.{cx}.{cz}.mcc").read_bytes()
                else:
                    payload = stream.read(length - 1)
                    if len(payload) != length - 1:
                        raise ValueError(f"Truncated chunk: {path}, chunk {index}")
                root = nbtlib.File.parse(io.BytesIO(decompress_chunk(payload, kind & 127)))
                root = root.get("Level", root)
                chunks += 1
                for section in root.get("sections", root.get("Sections", [])):
                    pos = (cx * 16, int(section["Y"]) * 16, cz * 16)
                    if bounds is not None and (pos[1] >= bounds[1][1] or pos[1] + 16 <= bounds[0][1]):
                        continue
                    storage = section.get("block_states", {})
                    palette = [state_key(e) for e in storage.get("palette", [])]
                    if not palette or all(p[0] in AIR for p in palette):
                        continue
                    local = decode_indices(storage.get("data", []), len(palette))
                    table = []
                    for key in palette:
                        if key not in ids:
                            ids[key] = len(states)
                            states.append(key)
                        table.append(ids[key])
                    sections.append((pos, np.asarray(table, dtype=np.uint32)[local].reshape(16, 16, 16)))
                    if len(sections) * 4096 > 32 * 1024 * 1024:
                        raise ValueError("Too many occupied sections; specify smaller --min/--max bounds")
    return states, sections, {"regionFiles": len(files), "chunksRead": chunks, "nonAirSections": len(sections)}


def game_shapes(states, prism):
    jar = prism / "libraries/com/mojang/minecraft/26.3/minecraft-26.3-client.jar"
    meta = json.loads((prism / "meta/net.minecraft/26.3.json").read_text(encoding="utf-8"))
    libraries = [jar]
    for lib in meta["libraries"]:
        group, artifact, version, *classifier = lib["name"].split(":")
        filename = artifact + "-" + version + ("-" + classifier[0] if classifier else "") + ".jar"
        path = prism / "libraries" / group.replace(".", "/") / artifact / version / filename
        if path.exists():
            libraries.append(path)
    java = prism / "java/java-runtime-epsilon/bin"
    with tempfile.TemporaryDirectory(prefix="chroma-shapes-") as directory:
        temp = Path(directory)
        source = temp / "ExportChromaShapes.java"
        source.write_text(SHAPE_JAVA, encoding="utf-8")
        (temp / "states.json").write_text(json.dumps([{"name": n, "properties": dict(p)} for n, p in states]), encoding="utf-8")
        cp = os.pathsep.join(map(str, [temp, *libraries]))
        for command in ([str(java / "javac.exe"), "-encoding", "UTF-8", "-cp", cp, str(source)], [str(java / "java.exe"), "-Xmx1G", "-cp", cp, "ExportChromaShapes", str(temp / "states.json"), str(temp / "shapes.json")]):
            run = subprocess.run(command, cwd=temp, capture_output=True, text=True, encoding="utf-8", errors="replace")
            if run.returncode:
                raise RuntimeError("Installed Minecraft shape extraction failed:\n" + run.stdout[-4000:] + run.stderr[-4000:])
        return json.loads((temp / "shapes.json").read_text(encoding="utf-8"))


def box_voxels(box):
    box = np.asarray(box, dtype=float)
    if box.shape != (6,) or not np.isfinite(box).all() or np.any(box[3:] <= box[:3]):
        raise ValueError(f"Invalid box: {box}")
    return np.floor(box[:3] * CPB + 1e-7).astype(int), np.ceil(box[3:] * CPB - 1e-7).astype(int)


def layout(lo, hi):
    lo, hi = np.asarray(lo, dtype=float), np.asarray(hi, dtype=float)
    if not np.isfinite([lo, hi]).all() or np.any(hi <= lo):
        raise ValueError("Bounds must be finite, nonempty, and maximum exclusive")
    origin = np.floor(lo / 16).astype(int) * 16
    dims = np.ceil((hi - origin) * CPB / 64).astype(int) * 64
    width, height = int(dims[0] // 16 * dims[2]), int(dims[1])
    if width > MAX_TEXTURE or height > MAX_TEXTURE or math.prod(map(int, dims)) > MAX_VOXELS:
        raise ValueError(f"Volume {dims.tolist()} needs {width}x{height} texture / {math.prod(map(int, dims)):,} cells; limit is {MAX_TEXTURE} per texture axis and {MAX_VOXELS:,} cells. Use smaller --min/--max bounds.")
    return origin, dims


def fill_box(volume, origin, box, clip):
    box = np.asarray(box, dtype=float)
    box[:3] = np.maximum(box[:3], clip[0])
    box[3:] = np.minimum(box[3:], clip[1])
    if np.any(box[3:] <= box[:3]):
        return
    lo, hi = box_voxels(box)
    lo -= origin * CPB
    hi -= origin * CPB
    volume[lo[1]:hi[1], lo[2]:hi[2], lo[0]:hi[0]] = 3


def pack(volume):
    """Input axis order Y,Z,X; sixteen x cells per RGBA pixel, little-endian pairs."""
    y, z, x = volume.shape
    if x % 16 or np.any(volume > 3):
        raise ValueError("Packing requires 16-cell x alignment and 2-bit values")
    grouped = volume.reshape(y, z * (x // 16), 4, 4)
    return np.bitwise_or.reduce(grouped << np.array([0, 2, 4, 6], dtype=np.uint8), axis=3)


def reduce_volume(volume):
    y, z, x = volume.shape
    return volume.reshape(y // 2, 2, z // 2, 2, x // 2, 2).max(axis=(1, 3, 5))


def export(args):
    bounds = None if args.minimum is None else (np.array(args.minimum), np.array(args.maximum))
    report = {"cellsPerBlock": CPB, "dimension": args.dimension, "unsupported": [], "ignoredNonOccluding": [], "approximatedCollisionStates": []}
    if args.fixture:
        fixture = json.loads(args.fixture.read_text(encoding="utf-8-sig"))
        boxes = [list(b["min"]) + list(b["max"]) if isinstance(b, dict) else list(b) for b in fixture["boxes"]]
        for box in boxes:
            box_voxels(box)
        if not boxes:
            raise ValueError("Fixture has no boxes")
        if bounds is None:
            bounds = (np.min(np.array(boxes)[:, :3], axis=0), np.max(np.array(boxes)[:, 3:], axis=0))
        origin, dims = layout(*bounds)
        volume = np.zeros((dims[1], dims[2], dims[0]), dtype=np.uint8)
        for box in boxes:
            fill_box(volume, origin, box, bounds)
        report.update(sourceFixture=str(args.fixture.resolve()), boxes=len(boxes))
    else:
        states, sections, stats = read_sections(args.world, args.dimension, bounds)
        shapes = game_shapes(states, args.prism)
        masks = []
        for state, shape in zip(states, shapes):
            mask = np.zeros((CPB, CPB, CPB), dtype=np.uint8)
            for box in shape["boxes"]:
                if min(box[:3]) < 0 or max(box[3:]) > 1:
                    shape["unsupported"] = "Occlusion shape exceeds one block"
                    break
                fill_box(mask, np.zeros(3, dtype=int), box, ([0, 0, 0], [1, 1, 1]))
            if "unsupported" in shape:
                mask[:] = 0
                report["unsupported"].append({"state": state_label(state), "reason": shape["unsupported"]})
            elif not mask.any() and state[0] not in AIR:
                report["ignoredNonOccluding"].append(state_label(state))
            elif mask.any() and shape.get("collisionApproximation"):
                report["approximatedCollisionStates"].append(state_label(state))
            masks.append(mask)
        masks = np.asarray(masks, dtype=np.uint8)
        solid = masks.any(axis=(1, 2, 3)) if len(masks) else np.array([], dtype=bool)
        if bounds is None:
            lo, hi = np.full(3, np.inf), np.full(3, -np.inf)
            for pos, cells in sections:
                ys, zs, xs = np.nonzero(solid[cells])
                if len(xs):
                    points = np.stack((xs, ys, zs), axis=1) + pos
                    lo = np.minimum(lo, points.min(axis=0))
                    hi = np.maximum(hi, points.max(axis=0) + 1)
            if not np.isfinite(lo).all():
                raise ValueError("No shadow-occluding blocks found")
            bounds = lo, hi
        origin, dims = layout(*bounds)
        volume = np.zeros((dims[1], dims[2], dims[0]), dtype=np.uint8)
        clip_lo = np.floor((bounds[0] - origin) * CPB + 1e-7).astype(int)
        clip_hi = np.ceil((bounds[1] - origin) * CPB - 1e-7).astype(int)
        counts = Counter()
        for pos, cells in sections:
            for state_id in np.unique(cells):
                if not solid[state_id]:
                    continue
                ys, zs, xs = np.nonzero(cells == state_id)
                for x, y, z in zip(xs, ys, zs):
                    block = np.array(pos) + [x, y, z]
                    if np.any(block >= bounds[1]) or np.any(block + 1 <= bounds[0]):
                        continue
                    # Quarter-block stencil preserves native slab/stair orientations.
                    start = (block - origin) * CPB
                    lo, hi = np.maximum(start, clip_lo), np.minimum(start + CPB, clip_hi)
                    a, b = lo - start, hi - start
                    stencil = masks[state_id, a[1]:b[1], a[2]:b[2], a[0]:b[0]]
                    if stencil.any():
                        volume[lo[1]:hi[1], lo[2]:hi[2], lo[0]:hi[0]] |= stencil
                        counts[state_label(states[state_id])] += 1
        report.update(stats, sourceWorld=str(args.world.resolve()), minecraftVersion="26.3", shapeSource="Installed vanilla occlusion shapes, with opaque modeled-block collision fallback", occluderStates=dict(counts))
    report.update(origin=origin.tolist(), dims=dims.tolist(), bounds={"min":np.asarray(bounds[0]).tolist(), "max":np.asarray(bounds[1]).tolist()}, occupiedCells=int(np.count_nonzero(volume)), textures={"base":"volume.png", "lod1":"volume_lod1.png", "lod2":"volume_lod2.png"}, limitations=["Saved static block geometry only; re-export after block changes.", "No entities, resource-pack model overrides, alpha-tested texture holes, or colored transmission.", "Glass, transparent blocks, fluids, leaves and noncolliding detailed models do not cast baked shadows.", "Collision fallback treats the body as opaque and clips it to its owning block; open gates retain only their occlusion posts.", "Conservative quarter-block occupancy can thicken details smaller than 0.25 blocks."])
    args.output.mkdir(parents=True, exist_ok=True)
    for filename in report["textures"].values():
        Image.fromarray(pack(volume), "RGBA").save(args.output / filename)
        volume = reduce_volume(volume)
    (args.output / "metadata.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"output":str(args.output.resolve()), "origin":report["origin"], "dims":report["dims"], "occupiedCells":report["occupiedCells"], "unsupported":report["unsupported"]}, ensure_ascii=False))


def check(prism):
    assert state_key("minecraft:stone") == state_key({"": "minecraft:stone"}) == state_key({"Name": "minecraft:stone"})
    assert state_key({"id":"minecraft:oak_slab", "properties":{"type":"top"}})[1] == (("type", "top"),)
    palette_size, bits = 19, 5
    indices = np.arange(4096, dtype=np.uint64) % palette_size
    words = np.zeros((4096 + 64 // bits - 1) // (64 // bits), dtype=np.uint64)
    np.bitwise_or.at(words, np.arange(4096) // (64 // bits), indices << ((np.arange(4096, dtype=np.uint64) % (64 // bits)) * bits))
    assert np.array_equal(decode_indices(words.view(np.int64), palette_size), indices)
    origin, dims = layout([-3, -2, -1], [3, 2, 1])
    assert origin.tolist() == [-16, -16, -16] and dims.tolist() == [128, 128, 128]
    v = np.zeros((64, 64, 64), dtype=np.uint8)
    for x in range(16):
        v[3, 2, x] = x % 4
    assert pack(v)[3, 2 * 4].tolist() == [228] * 4
    v[5, 7, 63] = 3
    assert reduce_volume(v)[2, 3, 31] == 3
    fixture = np.zeros((4, 4, 4), dtype=np.uint8)
    fill_box(fixture, np.zeros(3, dtype=int), [0, 0, 0, 1, .5, 1], ([0,0,0],[1,1,1]))
    assert np.count_nonzero(fixture) == 32 and not fixture[2:].any()
    try:
        layout([0, 0, 0], [1024, 1024, 1024])
    except ValueError:
        pass
    else:
        raise AssertionError("Oversized export must fail before allocating")
    doors = [state_key({"id":"minecraft:oak_door", "properties":{"open":value, "facing":"north", "hinge":"left"}}) for value in ("false", "true")]
    gates = [state_key({"id":"minecraft:oak_fence_gate", "properties":{"open":value}}) for value in ("false", "true")]
    shapes = game_shapes(doors + gates + [state_key(name) for name in ("minecraft:glass", "minecraft:glass_pane", "minecraft:oak_leaves", "minecraft:water", "minecraft:short_grass")], prism)
    door_masks = []
    for shape in shapes[:2]:
        assert "unsupported" not in shape and shape["boxes"], shape
        mask = np.zeros((4,4,4), dtype=np.uint8)
        for box in shape["boxes"]:
            fill_box(mask, np.zeros(3,dtype=int), box, ([0,0,0],[1,1,1]))
        door_masks.append(mask)
    assert np.count_nonzero(door_masks[0]) == np.count_nonzero(door_masks[1]) == 16
    assert not np.array_equal(*door_masks), "Opening a door must rotate its opaque quarter-cell sheet"
    assert shapes[2]["boxes"] != shapes[3]["boxes"] and shapes[3]["boxes"], "Open gates retain posts while removing their closed collision body"
    assert all(not shape["boxes"] and "unsupported" not in shape for shape in shapes[4:]), shapes[4:]
    print("PASS: palette storage, negative bounds, RGBA packing, OR mips, slab rasterization, size guard, native closed/open doors and gates, transparent exclusions")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--world", type=Path)
    source.add_argument("--fixture", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--dimension", default="minecraft:overworld")
    parser.add_argument("--min", dest="minimum", type=float, nargs=3, metavar=("X", "Y", "Z"))
    parser.add_argument("--max", dest="maximum", type=float, nargs=3, metavar=("X", "Y", "Z"))
    parser.add_argument("--prism", type=Path, default=Path(os.environ.get("APPDATA", ".")) / "PrismLauncher")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        check(args.prism)
        return
    if (args.world is None and args.fixture is None) or args.output is None:
        parser.error("Provide --world or --fixture and --output")
    if (args.minimum is None) != (args.maximum is None):
        parser.error("Provide both --min and --max")
    try:
        export(args)
    except (ValueError, OSError, RuntimeError) as error:
        parser.exit(1, f"Export failed: {error}\n")


if __name__ == "__main__":
    main()
