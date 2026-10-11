"""Check texture transport, alpha coverage, normal orientation and pack conversion."""
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile
import json

import numpy as np
from PIL import Image

import normal_maps as nm


def png(rgba):
    stream = BytesIO()
    Image.fromarray(np.asarray(rgba, dtype=np.uint8)).save(stream, format='PNG')
    return stream.getvalue()


def check_transport():
    rng = np.random.default_rng(928)
    rgba = rng.integers(0, 256, (16, 16, 4), dtype=np.uint8)
    rgba[..., 3] = 255
    quantized = rng.integers(0, 15, (16, 16, 2))
    slopes = (quantized - 7).astype(np.float32) / 7
    encoded = nm.encode_texture(rgba, slopes)
    for dy in range(4):
        for dx in range(4):
            assert np.array_equal(encoded[dy::4, dx::4, :3], rgba[..., :3])
    alpha = encoded[..., 3].astype(int)
    assert set(np.unique(alpha)) == {0, 255}  # Native classification stays cutout.
    mip1 = (alpha[::2, ::2] + alpha[::2, 1::2] +
            alpha[1::2, ::2] + alpha[1::2, 1::2]) // 4
    assert np.all(mip1 == 191)
    mip2 = (mip1[::2, ::2] + mip1[::2, 1::2] +
            mip1[1::2, ::2] + mip1[1::2, 1::2]) // 4
    assert np.all(mip2 == 191)
    for y in range(64):
        for x in range(64):
            decoded = nm.decode_pixel(encoded, x, y)
            assert decoded is not None and decoded[2] == 255
            assert np.array_equal(decoded[0], rgba[y // 4, x // 4, :3])
            assert np.allclose(decoded[1], slopes[y // 4, x // 4])
    rgba[4:8, 4:8, 3] = 0
    cutout = nm.encode_texture(rgba, slopes)
    assert np.all(cutout[16:32, 16:32, 3] == 0)
    assert nm.decode_pixel(cutout, 16, 16) is None
    assert np.all(cutout[16:32, 16:32, :3] == np.repeat(
        np.repeat(rgba[4:8, 4:8, :3], 4, 0), 4, 1))
    native = np.full((4, 4, 4), 255, dtype=np.uint8)
    assert all(nm.decode_pixel(native, x, y) is None for y in range(4) for x in range(4))
    for tiny_alpha in range(6):
        native[..., 3] = tiny_alpha
        assert nm.decode_pixel(native, 0, 0) is None  # Native destroy_oit textures.
        faint_pattern = encoded[:4, :4].copy()
        faint_pattern[..., 3] = np.where(faint_pattern[..., 3] > 0, tiny_alpha, 0)
        assert nm.decode_pixel(faint_pattern, 0, 0) is None  # Native pumpkin blur.
    broken = encoded.copy()
    broken[1, 0, 3] = 255 - broken[1, 0, 3]
    assert nm.decode_pixel(broken, 0, 0) is None
    broken = encoded.copy()
    broken[0, 1, 0] ^= 1
    assert nm.decode_pixel(broken, 1, 1) is None
    # Every corner works, including a caller-supplied offset sprite origin.
    padded = np.pad(encoded, ((3, 2), (5, 2), (0, 0)))
    assert nm.decode_pixel(padded, 5, 3, origin=(5, 3)) is not None
    assert nm.decode_pixel(encoded[:1], 0, 0) is None
    translucent = rgba.copy()
    translucent[0, 0, 3] = 127
    try:
        nm.encode_texture(translucent, slopes)
    except ValueError:
        pass
    else:
        raise AssertionError('Fractional alpha must not be repurposed')


def check_normals():
    normal = np.array([[[128, 128, 255, 255], [255, 128, 255, 255],
                        [128, 255, 255, 255], [0, 128, 255, 255]]], dtype=np.uint8)
    assert np.array_equal(nm.authored_slopes(normal), [[[0, 0], [1, 0], [0, 1], [-1, 0]]])
    surface = np.full((4, 4, 4), 255, dtype=np.uint8)
    surface[..., :3] = 128
    encoded = nm.encode_texture(surface, nm.generated_slopes(surface))
    assert np.array_equal(nm.decode_pixel(encoded, 0, 0)[1], [0, 0])
    # All225 valid normal codes, including the upper quantization boundary.
    yy, xx = np.indices((15, 15))
    every = np.stack([xx, yy], axis=-1).astype(np.float32) / 7 - 1
    all_encoded = nm.encode_texture(np.full((15, 15, 4), 255, dtype=np.uint8), every)
    for y in range(15):
        for x in range(15):
            assert np.allclose(nm.decode_pixel(all_encoded, x * 4, y * 4)[1], every[y, x])
    rng = np.random.default_rng(61)
    for _ in range(128):
        x0, y0, x1, y1 = rng.integers(0, 15, 4)
        a = all_encoded[y0 * 4:y0 * 4 + 4, x0 * 4:x0 * 4 + 4].astype(float)
        b = all_encoded[y1 * 4:y1 * 4 + 4, x1 * 4:x1 * 4 + 4].astype(float)
        for t in [0, 0.02, 0.2, 0.49, 0.5, 0.51, 0.8, 0.98, 1]:
            interpolated = (a * (1 - t) + b * t).astype(np.uint8)
            decoded = nm.decode_pixel(interpolated, 2, 3)
            assert decoded is not None and decoded[2] == 255
            assert np.all(np.abs(decoded[1]) <= 1)
            # Fractional animation coverage remains proportional to original.
            fade = a.copy()
            fade[..., 3] *= t
            faded = nm.decode_pixel(fade.astype(np.uint8), 1, 2)
            assert (faded is None) if int(255 * t) < 6 else faded[2] == int(255 * t)
    # A bright transparent texel cannot produce a rim on its opaque neighbour.
    surface[2, 2, :] = [255, 255, 255, 0]
    assert np.all(nm.generated_slopes(surface) == 0)
    ramp = np.full((4, 4, 4), 255, dtype=np.uint8)
    ramp[..., :3] = np.arange(4, dtype=np.uint8)[None, :, None] * 60
    assert np.all(nm.generated_slopes(ramp)[..., 0] < 0)
    ramp[..., :3] = np.arange(4, dtype=np.uint8)[:, None, None] * 60
    assert np.all(nm.generated_slopes(ramp)[..., 1] > 0)
    frames = np.full((8, 4, 4), 255, dtype=np.uint8)
    frames[:4, :, :3] = 0
    assert np.all(nm.generated_slopes(frames, {'animation': {}}) == 0)
    assert nm.frame_size((4, 8), {}) == (4, 8)
    assert nm.frame_size((8, 4), {'animation': {'height': 2}}) == (8, 2)
    metadata = {'animation': {'width': 4, 'height': 4, 'interpolate': True,
                              'frames': [1, {'index': 0, 'time': 3}]},
                'texture': {'blur': False}}
    converted = nm.encoded_metadata(metadata)
    assert converted['animation']['width'] == converted['animation']['height'] == 16
    assert converted['animation']['frames'] == metadata['animation']['frames']
    assert converted['animation']['interpolate'] is True
    assert converted['texture'] == {'blur': False, 'mipmap_strategy': 'mean'}
    assert metadata['animation']['width'] == 4


def check_pack():
    with TemporaryDirectory(prefix='chroma-normals-') as temp:
        root = Path(temp)
        source = root / 'source'
        block = source / 'assets/minecraft/textures/block'
        block.mkdir(parents=True)
        custom = source / 'assets/test/textures/custom'
        custom.mkdir(parents=True)
        model = source / 'assets/test/models/item/example.json'
        model.parent.mkdir(parents=True)
        model.write_text('{"textures":{"all":"test:custom/example"}}', encoding='utf-8')
        generated = model.with_name('generated.json')
        generated.write_text('{"parent":"minecraft:item/generated","textures":'
                             '{"layer0":"#base","base":"test:custom/example"}}', encoding='utf-8')
        child = model.with_name('child.json')
        child.write_text('{"parent":"test:item/generated","display":{"gui":{"scale":[1,1,1]}}}', encoding='utf-8')
        (source / 'pack.mcmeta').write_text('{"pack":{"description":"Example","min_format":[97,1],"max_format":[97,1]}}')
        flat = np.full((4, 4, 4), 255, dtype=np.uint8)
        flat[..., :3] = 128
        (block / 'solid.png').write_bytes(png(flat))
        fractional = flat.copy()
        fractional[..., 3] = 100
        transparent_bytes = png(fractional)
        (block / 'glass.png').write_bytes(transparent_bytes)
        (block / 'glass.png.mcmeta').write_text('{"texture":{"blur":true}}')
        (custom / 'example.png').write_bytes(png(flat))
        normals = flat.copy()
        normals[..., :3] = [255, 128, 255]
        (custom / 'example_n.png').write_bytes(png(normals))
        result = nm.convert_pack(source, root / 'output')
        assert result['converted'] == 2 and result['authored'] == 1
        assert result['unchanged_translucent'] == 1
        assert result['protected_generated_items'] == 3
        assert (root / 'output/assets/test/models/item/example.json').read_bytes() == model.read_bytes()
        assert (root / 'output/assets/minecraft/textures/block/glass.png').read_bytes() == transparent_bytes
        assert (root / 'output/assets/minecraft/textures/block/glass.png.mcmeta').read_bytes() == (
            block / 'glass.png.mcmeta').read_bytes()
        encoded = nm.image_rgba((root / 'output/assets/test/textures/custom/example.png').read_bytes())
        assert np.array_equal(nm.decode_pixel(encoded, 0, 0)[1], [1, 0])
        manifest = json.loads((root / 'output/assets/chroma/normal_maps.json').read_text())
        assert len(manifest['materials']) == 2
        assert not any(name.endswith('_n.png') for name in manifest['materials'])
        assert manifest['generated_items_original_textures'] == [
            'minecraft:item/glass_pane', 'test:item/child', 'test:item/generated']
        clone = root / 'output/assets/chroma/textures/item/chroma_normal_original/test/custom/example.png'
        assert clone.read_bytes() == (custom / 'example.png').read_bytes()
        for model_name in ('generated', 'child'):
            baked = json.loads((root / f'output/assets/test/models/item/{model_name}.json').read_text())
            assert baked['textures']['layer0'] == 'chroma:item/chroma_normal_original/test/custom/example'
        assert json.loads((root / 'output/assets/test/models/item/child.json').read_text())['display'] == {
            'gui': {'scale': [1, 1, 1]}}
        try:
            nm.convert_pack(root / 'output', root / 'doubled')
        except ValueError:
            pass
        else:
            raise AssertionError('Already encoded source was silently expanded again')
        archive_path = root / 'source.zip'
        with ZipFile(archive_path, 'w') as archive:
            for path in source.rglob('*'):
                if path.is_file():
                    archive.write(path, path.relative_to(source).as_posix())
        assert nm.convert_pack(archive_path, root / 'zipped')['converted'] == 2
        with ZipFile(root / 'unsafe.zip', 'w') as archive:
            archive.writestr('../escape', 'bad')
        try:
            nm.convert_pack(root / 'unsafe.zip', root / 'bad')
        except ValueError:
            pass
        else:
            raise AssertionError('ZIP traversal accepted')
        assert not (root / 'escape').exists()
        # No installed game is required to protect a vanilla generated item
        # overridden by a texture-only pack with an authored normal sidecar.
        item = source / 'assets/minecraft/textures/item'
        item.mkdir(parents=True)
        (item / 'diamond_sword.png').write_bytes(png(flat))
        (item / 'diamond_sword_n.png').write_bytes(png(normals))
        portable = root / 'portable'
        nm.convert_pack(source, portable, client_jar=root / 'missing-client.jar')
        sword = json.loads((portable / 'assets/minecraft/models/item/diamond_sword.json').read_text())
        assert sword['textures']['layer0'] == 'chroma:item/chroma_normal_original/minecraft/item/diamond_sword'
        assert (portable / 'assets/chroma/textures/item/chroma_normal_original/minecraft/item/diamond_sword.png').read_bytes() == png(flat)
        # Updating an opaque source to real translucency removes our stale .mcmeta.
        assert (portable / 'assets/minecraft/textures/block/solid.png.mcmeta').is_file()
        (block / 'solid.png').write_bytes(transparent_bytes)
        nm.convert_pack(source, portable, client_jar=root / 'missing-client.jar')
        assert not (portable / 'assets/minecraft/textures/block/solid.png.mcmeta').exists()
        assert (portable / 'assets/minecraft/textures/block/solid.png').read_bytes() == transparent_bytes
        # Removing the last authored map for an item restores its original image
        # and removes the old generated-item override, clone and encoded metadata.
        (item / 'diamond_sword_n.png').unlink()
        nm.convert_pack(source, portable, client_jar=root / 'missing-client.jar')
        for name in ('assets/minecraft/models/item/diamond_sword.json',
                     'assets/minecraft/textures/item/diamond_sword_n.png',
                     'assets/minecraft/textures/item/diamond_sword.png.mcmeta',
                     'assets/chroma/textures/item/chroma_normal_original/minecraft/item/diamond_sword.png'):
            assert not (portable / name).exists(), name
        assert (portable / 'assets/minecraft/textures/item/diamond_sword.png').read_bytes() == png(flat)
        (block / 'solid.png').write_bytes(png(flat))
        nm.convert_pack(source, portable, client_jar=root / 'missing-client.jar')
        assert (portable / 'assets/minecraft/textures/block/solid.png.mcmeta').exists()
    if nm.CLIENT_JAR.exists():
        with ZipFile(nm.CLIENT_JAR) as archive:
            wool = nm.image_rgba(archive.read('assets/minecraft/textures/block/light_blue_wool.png'))
        assert all(nm.decode_pixel(wool, x, y) is None
                   for y in range(wool.shape[0]) for x in range(wool.shape[1]))


def check_native_textures():
    """Scan every4x4 window, not just aligned texels, for accidental signatures."""
    if not nm.CLIENT_JAR.exists():
        return 0
    count = 0
    with ZipFile(nm.CLIENT_JAR) as archive:
        for name in archive.namelist():
            # Native mobs and screen overlays also pass through shared hooks.
            # Fonts have separate, unmodified text shaders and never decode.
            if (not name.startswith('assets/minecraft/textures/') or not name.endswith('.png')
                    or name.startswith('assets/minecraft/textures/font/')):
                continue
            count += 1
            rgba = nm.image_rgba(archive.read(name))
            if min(rgba.shape[:2]) < 4:
                continue
            alpha = rgba[..., 3].astype(np.int16)
            samples = np.stack([alpha[:-1, :-1], alpha[:-1, 1:],
                                alpha[1:, :-1], alpha[1:, 1:]])
            top = samples.max(axis=0)
            quads = ((top > 0) & ((samples >= top - 1).sum(axis=0) >= 2) &
                     (np.abs(samples.sum(axis=0) - 3 * top) <= 2))
            candidates = quads[:-2, :-2] & quads[:-2, 2:] & quads[2:, :-2] & quads[2:, 2:]
            for y, x in zip(*np.nonzero(candidates)):
                assert nm.decode_pixel(rgba, x, y, origin=(x, y)) is None, (name, x, y)
    return count


def check_obsolete_outputs():
    for legacy in (False, True):
        with TemporaryDirectory(prefix='chroma-normal-update-') as temp:
            root = Path(temp)
            source, output = root / 'source', root / 'output'
            block = source / 'assets/minecraft/textures/block'
            block.mkdir(parents=True)
            data = png(np.full((4, 4, 4), 255, dtype=np.uint8))
            for name in ('dandelion', 'stone'):
                (block / (name + '.png')).write_bytes(data)
            (block / 'dandelion.png.mcmeta').write_text('{"texture":{"blur":false}}')
            model = source / 'assets/test/models/item/flower.json'
            model.parent.mkdir(parents=True)
            model.write_text('{"parent":"item/generated","textures":{"layer0":"block/dandelion"}}')
            (source / 'copied.txt').write_text('source-owned copy')
            try:
                nm.convert_pack(source, root)
            except ValueError as error:
                assert 'separate from the source' in str(error)
            else:
                raise AssertionError('Output ancestor can overwrite source files')
            nm.convert_pack(source, output)
            (output / 'unrelated.txt').write_text('keep my notes')
            manifest_path = output / 'assets/chroma/normal_maps.json'
            manifest = json.loads(manifest_path.read_text())
            assert manifest['owned_files']['copied.txt']
            if legacy:
                del manifest['owned_files']
                manifest_path.write_text(json.dumps(manifest))
            for path in (block / 'dandelion.png', block / 'dandelion.png.mcmeta', model, source / 'copied.txt'):
                path.unlink()
            result = nm.convert_pack(source, output)
            assert result['removed_obsolete_files'] >= 6
            for name in ('assets/minecraft/textures/block/dandelion.png',
                         'assets/minecraft/textures/block/dandelion.png.mcmeta',
                         'assets/minecraft/models/item/dandelion.json',
                         'assets/test/models/item/flower.json',
                         'assets/chroma/textures/item/chroma_normal_original/minecraft/block/dandelion.png',
                         'assets/chroma/textures/item/chroma_normal_original/minecraft/block/dandelion.png.mcmeta'):
                assert not (output / name).exists(), (legacy, name)
            assert (output / 'unrelated.txt').read_text() == 'keep my notes'
            assert (output / 'copied.txt').exists() == legacy  # Older manifests never recorded arbitrary copies.
            # Refuse to delete a formerly owned file changed by the user.
            (block / 'dandelion.png').write_bytes(data)
            nm.convert_pack(source, output)
            clone = output / 'assets/chroma/textures/item/chroma_normal_original/minecraft/block/dandelion.png'
            clone.write_bytes(b'my deliberate edit')
            (block / 'dandelion.png').unlink()
            try:
                nm.convert_pack(source, output)
            except ValueError as error:
                assert 'modified outside the converter' in str(error)
            else:
                raise AssertionError('Modified obsolete asset was silently deleted')
            assert clone.read_bytes() == b'my deliberate edit'
            assert (output / 'assets/minecraft/textures/block/dandelion.png').exists()
            # Even a tampered ownership manifest cannot target outside output.
            manifest = json.loads(manifest_path.read_text())
            manifest['owned_files']['../outside.txt'] = '0' * 64
            manifest_path.write_text(json.dumps(manifest))
            (root / 'outside.txt').write_text('outside')
            try:
                nm.convert_pack(source, output)
            except ValueError as error:
                assert 'Unsafe output resource path' in str(error)
            else:
                raise AssertionError('Ownership traversal was accepted')
            assert (root / 'outside.txt').read_text() == 'outside'
    # An existing overlay can be updated down to zero encoded textures.
    with TemporaryDirectory(prefix='chroma-last-normal-') as temp:
        root = Path(temp)
        source, output = root / 'source', root / 'output'
        item = source / 'assets/minecraft/textures/item'
        item.mkdir(parents=True)
        data = png(np.full((4, 4, 4), 255, dtype=np.uint8))
        (item / 'diamond_sword.png').write_bytes(data)
        (item / 'diamond_sword_n.png').write_bytes(data)
        nm.convert_pack(source, output)
        (item / 'diamond_sword_n.png').unlink()
        assert nm.convert_pack(source, output)['converted'] == 0
        assert not (output / 'assets/minecraft/models/item/diamond_sword.json').exists()


def main():
    for texture in ('block/stone', 'entity/chest/normal', 'entity/banner/base',
                    'entity/bell/bell_body', 'entity/conduit/base', 'entity/cushion/red_cushion',
                    'entity/decorated_pot/decorated_pot_base', 'entity/shulker/shulker_red',
                    'entity/enchantment/enchanting_table_book', 'entity/skeleton/skeleton',
                    'entity/skeleton/wither_skeleton', 'entity/zombie/zombie',
                    'entity/creeper/creeper', 'entity/enderdragon/dragon', 'entity/piglin/piglin'):
        assert nm.is_vanilla_material(f'assets/minecraft/textures/{texture}.png')
    for texture in ('entity/shulker/spark', 'entity/player/wide/steve', 'entity/cow/cow_temperate',
                    'gui/signs/oak', 'entity/beacon/beacon_beam'):
        assert not nm.is_vanilla_material(f'assets/minecraft/textures/{texture}.png')
    check_transport()
    check_normals()
    check_pack()
    check_obsolete_outputs()
    native_count = check_native_textures()
    print(f'PASS: RGB, signature/mips, coverage, normals, animation, custom pack ownership/reruns; {native_count} native textures without collisions')


if __name__ == '__main__':
    main()
