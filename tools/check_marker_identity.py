"""CPU/native-asset marker identity checks; no GLSL execution or game launch.

Requires NumPy, Pillow and the installed Minecraft 26.3 JAR. Tests include the
real light-blue wool atlas-border collision, complete codes and GUI exclusion.
"""
from argparse import ArgumentParser
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile
import json
import os
import re

import numpy as np
from PIL import Image

import extract_core
import generate_markers

ROOT = Path(__file__).resolve().parents[1]
F = np.float32
KEY = np.array([76, 195], dtype=np.float32) / F(255)
OFFSETS = np.array([[0, 0], [1, 0], [-1, 0], [0, 1], [0, -1]], dtype=np.float32)


def stencil(pixels, xy, mip_levels):
    # Native 26.3 Stitcher pads every sprite by at least 1 << mip_levels.
    # textureLod(..., 0) reads the original pixels, regardless of other mips.
    padding = 1 << mip_levels
    padded = np.pad(pixels, ((padding, padding), (padding, padding), (0, 0)), mode='edge')
    atlas_size = np.array([2048, 1024], dtype=np.float32)
    origin = np.array([64, 64], dtype=np.float32)
    uv = (origin + np.array(xy, dtype=np.float32)) / atlas_size
    coords = np.floor((uv + OFFSETS / atlas_size) * atlas_size - origin).astype(int) + padding
    assert np.all(coords >= 0) and np.all(coords < [padded.shape[1], padded.shape[0]])
    return padded[coords[:, 1], coords[:, 0]].astype(np.float32) / F(255)


def old_match(samples):
    return bool(np.all(np.abs(samples[:, :2] - KEY) < F(3) / F(255)))


def match(samples, perspective=True):
    codes = np.floor(samples[:, 2] * F(255) + F(.5)).astype(int)
    return bool(perspective and old_match(samples) and
                np.all(samples[:, 3] >= F(254.5) / F(255)) and
                np.all((codes & 192) == 0) and np.all((codes & 7) <= 4) and
                np.all((codes & 39) == (codes[0] & 39)))


def rgba(data):
    return np.asarray(Image.open(BytesIO(data)).convert('RGBA'))


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--client-jar', type=Path, default=Path(os.environ.get('APPDATA', '.')) /
                        'PrismLauncher/libraries/com/mojang/minecraft/26.3/minecraft-26.3-client.jar')
    args = parser.parse_args()
    marker_cases = 0
    with ZipFile(args.client_jar) as jar:
        for stem in ('item', 'entity'):
            rel = f'assets/minecraft/shaders/core/{stem}.vsh'
            vanilla = jar.read(rel).decode('utf-8').replace('\r\n', '\n')
            assert (ROOT / rel).read_text(encoding='utf-8') == extract_core.transform(vanilla, 'vsh')
        helper = extract_core.VERTEX_HELPER
        for condition in ('value.a >= 254.5 / 255.0', '(code & 192) == 0',
                          '(code & 7) <= 4', '(code & 39) == identity'):
            assert condition in helper
        assert helper.count('chromaMatchSample(') == 6  # Declaration + all five samples.
        fetches = re.findall(r'textureLod\(Sampler0, ([^\n]+?)\)', helper)
        assert len(fetches) == 5 and helper.count('0.0), identity)') == 4
        assert 'textureLod(Sampler0, uv, 0.0)' in helper
        assert 'if (ProjMat[2][3] != 0.0 && chromaMatchKey(UV0, chromaTexel))' in extract_core.VERTEX_BRANCH

        wool = rgba(jar.read('assets/minecraft/textures/block/light_blue_wool.png'))
        assert wool[-1, -1].tolist() == [73, 194, 228, 255]
        wool_samples = stencil(wool, (16, 16), 4)
        assert old_match(wool_samples), 'Actual padded wool corner must expose the old defect'
        assert not match(wool_samples) and not match(wool_samples, perspective=False)
        old_code = int(np.floor(wool_samples[0, 2] * F(255) + F(.5)))
        assert (old_code & 7, (old_code >> 3) & 3, bool(old_code & 32)) == (4, 0, True)

        wool_count = 0
        for name in jar.namelist():
            if not name.startswith('assets/minecraft/textures/block/') or not name.endswith('_wool.png'):
                continue
            pixels = rgba(jar.read(name))
            for x, y in ((0, 0), (0, pixels.shape[0]), (pixels.shape[1], 0),
                         (pixels.shape[1], pixels.shape[0])):
                assert not match(stencil(pixels, (x, y), 4)), (name, x, y)
            wool_count += 1
        assert wool_count == 16

    for family, shape in generate_markers.FAMILIES.items():
        model = json.loads((ROOT / f'assets/chroma/models/custom/{family}.json').read_text())
        assert all(e['faces']['south']['uv'] == [2, 2, 6, 6] for e in model['elements'])
        for header in (False, True):
            name = family + ('_header' if header else '')
            data = (ROOT / f'assets/chroma/textures/custom/{name}.png').read_bytes()
            assert data == generate_markers.marker_png(shape, header)
            pixels = rgba(data)
            for mip_levels in range(5):
                for corner, xy in enumerate(((1, 1), (1, 3), (3, 3), (3, 1))):
                    samples = stencil(pixels, xy, mip_levels)
                    assert match(samples) and not match(samples, perspective=False)
                    code = int(np.floor(samples[0, 2] * F(255) + F(.5)))
                    assert code == shape + 8 * corner + 32 * header
                    marker_cases += 1

    # Each neighbor must independently reject reserved bits, invalid shapes,
    # mismatched shape/header or nonopaque textures; corner bits may differ.
    good = np.tile(np.array([76, 195, 0, 255], dtype=np.float32) / F(255), (5, 1))
    assert match(good)
    for index in range(5):
        for code in (5, 6, 7, 64, 128, 192, 228):
            bad = good.copy(); bad[index, 2] = F(code) / F(255)
            assert not match(bad), (index, code)
        bad = good.copy(); bad[index, 3] = F(254) / F(255)
        assert not match(bad)
    for index in range(1, 5):
        for code in (1, 32):
            bad = good.copy(); bad[index, 2] = F(code) / F(255)
            assert not match(bad)
        allowed = good.copy(); allowed[index, 2] = F(24) / F(255)
        assert match(allowed)
    print(f'PASS: actual wool collision rejected; {wool_count} wool textures, '
          f'{marker_cases} marker/mipmap-padding corners, GUI exclusion and generated shader parity.')
    print('CPU and source contracts only; GLSL compilation and live inventory rendering are separate checks.')


if __name__ == '__main__':
    main()
