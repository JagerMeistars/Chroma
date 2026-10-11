"""Bake tangent-space normal slopes into vanilla texture alpha (requires Chroma).

Pillow and NumPy are used by the existing resource-pack tools. Original RGB and
binary coverage are preserved; translucent textures are deliberately unchanged.
"""
from argparse import ArgumentParser
from copy import deepcopy
from hashlib import sha256
from io import BytesIO
from pathlib import Path, PurePosixPath
from zipfile import ZipFile
import json
import os

import numpy as np
from PIL import Image

FORMAT = 'chroma-normal-alpha-4x4-v1'
DEFAULT_STRENGTH = 2.0
CLIENT_JAR = Path(os.environ.get('APPDATA', '.')) / (
    'PrismLauncher/libraries/com/mojang/minecraft/26.3/minecraft-26.3-client.jar')
BLOCK_ENTITY_TEXTURE_DIRS = ('banner', 'bell', 'chest', 'conduit', 'cushion',
                            'decorated_pot', 'enchantment', 'shulker')
SKULL_TEXTURES = ('entity/skeleton/skeleton.png', 'entity/skeleton/wither_skeleton.png',
                 'entity/zombie/zombie.png', 'entity/creeper/creeper.png',
                 'entity/enderdragon/dragon.png', 'entity/piglin/piglin.png')


def is_vanilla_material(name):
    """26.3 block surfaces, including the separate block-entity texture atlases."""
    prefix = 'assets/minecraft/textures/'
    if not name.startswith(prefix) or not name.endswith('.png'):
        return False
    texture = name[len(prefix):]
    if texture.startswith('block/'):
        return True
    if texture in SKULL_TEXTURES:
        return True
    # Shulker box skins are shared with the mob; its projectile is unrelated.
    if texture == 'entity/shulker/spark.png':
        return False
    return texture.startswith(tuple(f'entity/{directory}/' for directory in BLOCK_ENTITY_TEXTURE_DIRS))


def image_rgba(data):
    with Image.open(BytesIO(data)) as image:
        return np.array(image.convert('RGBA'))


def frame_size(size, metadata):
    """Match vanilla animation frame defaults; static rectangles stay rectangles."""
    width, height = size
    animation = metadata.get('animation')
    if animation is None:
        return width, height
    if 'width' in animation:
        fw, fh = animation['width'], animation.get('height', height)
    elif 'height' in animation:
        fw, fh = width, animation['height']
    else:
        fw = fh = min(width, height)
    if (not isinstance(fw, int) or not isinstance(fh, int) or
            fw <= 0 or fh <= 0 or width % fw or height % fh):
        raise ValueError(f'Invalid animation frame size {fw}x{fh} for {width}x{height}')
    return fw, fh


def generated_slopes(rgba, metadata=None, strength=DEFAULT_STRENGTH):
    """Small height gradients, isolated per animation frame and alpha island."""
    if not np.isfinite(strength) or strength < 0:
        raise ValueError('Normal strength must be finite and nonnegative')
    height, width = rgba.shape[:2]
    fw, fh = frame_size((width, height), metadata or {})
    slopes = np.zeros((height, width, 2), dtype=np.float32)
    for y in range(0, height, fh):
        for x in range(0, width, fw):
            frame = rgba[y:y + fh, x:x + fw]
            luminance = (frame[..., :3].astype(np.float32) / 255) @ np.array(
                [0.2126, 0.7152, 0.0722], dtype=np.float32)
            occupied = frame[..., 3] > 0
            values = np.pad(luminance, 1, mode='edge')
            coverage = np.pad(occupied, 1, mode='edge')
            left = np.where(coverage[1:-1, :-2], values[1:-1, :-2], luminance)
            right = np.where(coverage[1:-1, 2:], values[1:-1, 2:], luminance)
            up = np.where(coverage[:-2, 1:-1], values[:-2, 1:-1], luminance)
            down = np.where(coverage[2:, 1:-1], values[2:, 1:-1], luminance)
            # OpenGL normal Y points up, opposite to image row coordinates.
            slopes[y:y + fh, x:x + fw, 0] = (left - right) * (strength * 0.5)
            slopes[y:y + fh, x:x + fw, 1] = (down - up) * (strength * 0.5)
    slopes[rgba[..., 3] == 0] = 0
    return np.clip(slopes, -1, 1)


def authored_slopes(normal_rgba):
    """OpenGL RGB normals: neutral 128 maps exactly to zero on either XY axis."""
    values = normal_rgba[..., :3].astype(np.float32)
    xy = np.where(values[..., :2] >= 128,
                  (values[..., :2] - 128) / 127,
                  (values[..., :2] - 128) / 128)
    z = np.maximum(values[..., 2] * (2 / 255) - 1, 1 / 255)
    return np.clip(xy / z[..., None], -1, 1)


def encode_texture(rgba, slopes):
    """Replicate RGB 4x4; each 2x2 quadrant's one alpha hole carries two bits."""
    if rgba.ndim != 3 or rgba.shape[2] != 4 or slopes.shape != (*rgba.shape[:2], 2):
        raise ValueError('Expected RGBA image and matching XY slope array')
    if np.any((rgba[..., 3] != 0) & (rgba[..., 3] != 255)):
        raise ValueError('Fractional alpha must remain unencoded')
    if not np.all(np.isfinite(slopes)):
        raise ValueError('Non-finite normal slope')
    q = np.floor(np.clip(slopes, -1, 1) * 7 + 7.5).astype(np.uint8)
    code = q[..., 0] + 15 * q[..., 1]
    out = np.repeat(np.repeat(rgba, 4, axis=0), 4, axis=1)
    yy, xx = np.indices(rgba.shape[:2])
    for quadrant in range(4):
        corner = (code >> (quadrant * 2)) & 3
        y = yy * 4 + (quadrant // 2) * 2 + (corner // 2)
        x = xx * 4 + (quadrant % 2) * 2 + (corner % 2)
        out[y, x, 3] = 0
    return out


def decode_pixel(pixels, x, y, origin=(0, 0)):
    """CPU reference: find an encoded cell from any of its sixteen texels.

    Returns (original RGB, XY slopes, coverage byte), or None for native data.
    A zero-alpha texel alone is intentionally not proof of an encoded texture.
    """
    x = ((x - origin[0]) // 4) * 4 + origin[0]
    y = ((y - origin[1]) // 4) * 4 + origin[1]
    if x < 0 or y < 0 or x + 3 >= pixels.shape[1] or y + 3 >= pixels.shape[0]:
        return None
    cell = pixels[y:y + 4, x:x + 4]
    a = cell[..., 3].astype(int)
    if not np.all(cell[..., :3] == cell[0, 0, :3]):
        return None
    code = 0
    coverage = None
    for quadrant in range(4):
        x0, y0 = (quadrant % 2) * 2, (quadrant // 2) * 2
        quad = a[y0:y0 + 2, x0:x0 + 2].reshape(4)
        top = int(quad.max())
        # Native animation interpolates RGBA. A moving hole becomes two partial
        # texels plus two opaque texels; the nearest-frame corner still decodes.
        if top < 6 or np.count_nonzero(quad >= top - 1) < 2 or abs(int(quad.sum()) - 3 * top) > 2:
            return None
        if coverage is not None and abs(coverage - top) > 1:
            return None
        coverage = top
        code |= int(np.argmin(quad)) << (quadrant * 2)
    if code >= 225:
        return None
    q = np.array([code % 15, code // 15], dtype=np.float32)
    return cell[0, 0, :3].copy(), (q - 7) / 7, coverage


def encoded_metadata(metadata):
    metadata = deepcopy(metadata)
    animation = metadata.get('animation', {})
    for key in ('width', 'height'):
        if key in animation:
            animation[key] *= 4
    # Required: encoded alpha must be averaged arithmetically, not coverage-cut.
    metadata.setdefault('texture', {})['mipmap_strategy'] = 'mean'
    return metadata


def output_path(output, name):
    """Validate manifest/source paths, including existing destination symlinks."""
    relative = PurePosixPath(name)
    if (not name or relative.is_absolute() or '..' in relative.parts or
            '\\' in name or ':' in name):
        raise ValueError(f'Unsafe output resource path: {name!r}')
    path = output / relative
    if output not in path.resolve().parents:
        raise ValueError(f'Output resource escapes destination: {name!r}')
    return path


def write_output(output, name, data, owned):
    path = output_path(output, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    owned[name] = sha256(data).hexdigest()


def previous_owned_files(output, manifest):
    if manifest.get('format') != FORMAT:
        return {}
    if 'owned_files' in manifest:
        owned = manifest['owned_files']
        if not isinstance(owned, dict):
            raise ValueError('Invalid owned_files in output manifest')
        for name, digest in owned.items():
            output_path(output, name)
            if not isinstance(digest, str) or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
                raise ValueError(f'Invalid output ownership checksum: {name!r}')
        return owned
    # Migrate older manifests narrowly. Unlisted copied files cannot be proven
    # converter-owned, so keep them. Snapshot these known paths before writing.
    names = set()
    for name in set(manifest.get('materials', {})) | set(manifest.get('skipped', {})):
        names.update((name, name + '.mcmeta'))
    for model_id in manifest.get('generated_items_original_textures', []):
        namespace, model = model_id.split(':', 1)
        name = f'assets/{namespace}/models/{model}.json'
        names.add(name)
        path = output_path(output, name)
        if path.is_file():
            for texture in json.loads(path.read_text(encoding='utf-8')).get('textures', {}).values():
                if isinstance(texture, str) and texture.startswith('chroma:item/chroma_normal_original/'):
                    clone = 'assets/chroma/textures/' + texture.split(':', 1)[1] + '.png'
                    names.update((clone, clone + '.mcmeta'))
    return {name: sha256(output_path(output, name).read_bytes()).hexdigest()
            for name in names if output_path(output, name).is_file()}


def remove_obsolete_outputs(output, previous, current):
    obsolete = []
    # Check the complete removal set before deleting anything; never discard
    # manual edits to a file that the current source no longer produces.
    for name in sorted(set(previous) - set(current)):
        path = output_path(output, name)
        if not path.exists():
            continue
        if not path.is_file() or sha256(path.read_bytes()).hexdigest() != previous[name]:
            raise ValueError(f'Obsolete output was modified outside the converter: {name}. '
                             'Keep that edit in the source pack or choose a fresh output directory.')
        obsolete.append(path)
    for path in obsolete:
        path.unlink()
    return len(obsolete)


def protect_generated_items(names, read, materials, output, owned, *, vanilla=False, client_jar=CLIENT_JAR):
    """Keep CPU-generated item side faces tied to original alpha silhouettes."""
    models = {}

    def load_models(entries, reader):
        for name in entries:
            parts = PurePosixPath(name).parts
            if len(parts) >= 4 and parts[0] == 'assets' and parts[2] == 'models' and name.endswith('.json'):
                model_id = parts[1] + ':' + '/'.join(parts[3:])[:-5]
                models[model_id] = json.loads(reader(name))

    # The downloaded converter must work without our PrismLauncher installation.
    # Source-pack definitions below take precedence over this bundled26.3 set.
    if not vanilla:
        registry = Path(__file__).with_name('normal_item_models.json')
        models.update(json.loads(registry.read_text(encoding='utf-8')))
    load_models(names, read)

    def qualified(identifier):
        return identifier if ':' in identifier else 'minecraft:' + identifier

    def inherited(identifier, visited=()):
        if identifier == 'minecraft:builtin/generated':
            return True, {}
        if identifier in visited:
            return False, {}
        model = models.get(identifier)
        if model is None:
            return identifier in ('minecraft:item/generated', 'minecraft:item/handheld',
                                   'minecraft:item/handheld_rod'), {}
        parent = model.get('parent', '')
        generated, textures = inherited(qualified(parent), (*visited, identifier)) if parent else (False, {})
        return generated, {**textures, **model.get('textures', {})}

    protected = []
    for model_id, model in sorted(models.items()):
        generated, textures = inherited(model_id)
        if not generated:
            continue
        overrides = {}
        for layer in ('layer0', 'layer1', 'layer2', 'layer3', 'layer4'):
            texture = textures.get(layer)
            seen = set()
            while isinstance(texture, str) and texture.startswith('#') and texture not in seen:
                seen.add(texture)
                texture = textures.get(texture[1:])
            if not isinstance(texture, str) or texture.startswith('#'):
                continue
            namespace, texture_path = qualified(texture).split(':', 1)
            source_name = f'assets/{namespace}/textures/{texture_path}.png'
            if source_name not in materials:
                continue
            # The native item atlas includes the item/ directory automatically.
            clone = f'item/chroma_normal_original/{namespace}/{texture_path}'
            write_output(output, f'assets/chroma/textures/{clone}.png', read(source_name), owned)
            if source_name + '.mcmeta' in names:
                write_output(output, f'assets/chroma/textures/{clone}.png.mcmeta', read(source_name + '.mcmeta'), owned)
            overrides[layer] = f'chroma:{clone}'
        if overrides:
            changed = deepcopy(model)
            changed['textures'] = {**changed.get('textures', {}), **overrides}
            namespace, model_path = model_id.split(':', 1)
            write_output(output, f'assets/{namespace}/models/{model_path}.json',
                         (json.dumps(changed, ensure_ascii=False, separators=(',', ':')) + '\n').encode('utf-8'), owned)
            protected.append(model_id)
    return protected


def convert_pack(source, output, *, vanilla=False, strength=DEFAULT_STRENGTH, client_jar=CLIENT_JAR):
    """Convert a source pack directory/ZIP, or block textures from a client JAR."""
    source, output = Path(source).resolve(), Path(output).resolve()
    if not source.exists():
        raise FileNotFoundError(source)
    if source == output or (source.is_dir() and (source in output.parents or output in source.parents)):
        raise ValueError('Output must be separate from the source pack')
    if not np.isfinite(strength) or strength < 0:
        raise ValueError('Normal strength must be finite and nonnegative')
    prior_path = output_path(output, 'assets/chroma/normal_maps.json')
    prior_manifest = json.loads(prior_path.read_text(encoding='utf-8')) if prior_path.is_file() else {}
    prior_owned = previous_owned_files(output, prior_manifest)
    archive = ZipFile(source) if source.is_file() else None
    try:
        names = sorted(n for n in archive.namelist() if not n.endswith('/')) if archive else sorted(
            p.relative_to(source).as_posix() for p in source.rglob('*') if p.is_file())
        for name in names:
            path = PurePosixPath(name)
            if path.is_absolute() or '..' in path.parts or '\\' in name or ':' in name:
                raise ValueError(f'Unsafe resource path: {name!r}')
        name_set = set(names)
        read = archive.read if archive else lambda name: (source / name).read_bytes()
        if not vanilla and 'assets/chroma/normal_maps.json' in name_set:
            previous = json.loads(read('assets/chroma/normal_maps.json'))
            if previous.get('format') == FORMAT:
                raise ValueError('Pack already contains encoded normal maps; convert the original source pack')
        textures = []
        for name in names:
            path = PurePosixPath(name)
            if not name.startswith('assets/') or '/textures/' not in name or path.suffix != '.png':
                continue
            if path.stem.endswith(('_n', '_s', '_e')):
                continue
            authored = str(path.with_name(path.stem + '_n.png'))
            if (is_vanilla_material(name) if vanilla else
                    '/textures/block/' in name or authored in name_set):
                textures.append((name, authored if authored in name_set else None))
        if not textures and (vanilla or not prior_owned):
            raise ValueError('Source contains no block textures or textures with *_n.png maps')
        output.mkdir(parents=True, exist_ok=True)
        owned = {}
        if not vanilla:
            for name in names:
                write_output(output, name, read(name), owned)
        manifest = {'format': FORMAT, 'height_strength': strength,
                    'materials': {}, 'authored_normals': {}, 'skipped': {}}
        for name, normal_name in textures:
            data = read(name)
            rgba = image_rgba(data)
            meta_name = name + '.mcmeta'
            metadata = json.loads(read(meta_name)) if meta_name in name_set else {}
            if np.any((rgba[..., 3] != 0) & (rgba[..., 3] != 255)):
                write_output(output, name, data, owned)
                if meta_name in name_set:
                    write_output(output, meta_name, read(meta_name), owned)
                manifest['skipped'][name] = 'fractional alpha preserved'
                continue
            if normal_name:
                normal_data = read(normal_name)
                normals = image_rgba(normal_data)
                if normals.shape[:2] != rgba.shape[:2]:
                    raise ValueError(f'Normal-map dimensions differ from diffuse: {normal_name}')
                slopes = authored_slopes(normals)
                manifest['authored_normals'][normal_name] = sha256(normal_data).hexdigest()
            else:
                slopes = generated_slopes(rgba, metadata, strength)
            buffer = BytesIO()
            Image.fromarray(encode_texture(rgba, slopes)).save(buffer, format='PNG')
            write_output(output, name, buffer.getvalue(), owned)
            write_output(output, meta_name,
                         (json.dumps(encoded_metadata(metadata), ensure_ascii=False, separators=(',', ':')) + '\n').encode('utf-8'), owned)
            manifest['materials'][name] = sha256(data).hexdigest()
        item_materials = set(manifest['materials'])
        if not vanilla:
            # The Chroma pack below an overlay may already redirect a flower's
            # generated item to an original clone. Keep custom translucent edits
            # visible there too, even though their normal map cannot be encoded.
            item_materials.update(manifest['skipped'])
        manifest['generated_items_original_textures'] = protect_generated_items(
            name_set, read, item_materials, output, owned, vanilla=vanilla, client_jar=client_jar)
        owned.pop('assets/chroma/normal_maps.json', None)  # A manifest cannot hash itself.
        removed = remove_obsolete_outputs(output, prior_owned, owned)
        manifest['owned_files'] = dict(sorted(owned.items()))
        manifest_path = output_path(output, 'assets/chroma/normal_maps.json')
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
        return {'converted': len(manifest['materials']), 'authored': len(manifest['authored_normals']),
                'unchanged_translucent': len(manifest['skipped']),
                'protected_generated_items': len(manifest['generated_items_original_textures']),
                'removed_obsolete_files': removed,
                'output': str(output)}
    finally:
        if archive:
            archive.close()


def main():
    parser = ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--source', type=Path, help='Custom resource-pack directory or ZIP')
    source.add_argument('--vanilla', action='store_true', help='Use installed vanilla block textures')
    parser.add_argument('--client-jar', type=Path, default=CLIENT_JAR)
    parser.add_argument('--output', type=Path, required=True, help='Output pack directory')
    parser.add_argument('--strength', type=float, default=DEFAULT_STRENGTH,
                        help='Generated height-gradient strength; authored maps are unchanged')
    args = parser.parse_args()
    result = convert_pack(args.client_jar if args.vanilla else args.source, args.output,
                          vanilla=args.vanilla, strength=args.strength, client_jar=args.client_jar)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
