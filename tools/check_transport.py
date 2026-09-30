"""CPU check for the generated camera-header ABI and packet pixel bounds.

This checks source and layout invariants; it does not simulate rasterization,
run Minecraft, or measure GPU performance.
"""
from argparse import ArgumentParser
from pathlib import Path
from zipfile import ZipFile
import json
import os

import extract_core


def capacity(width, height):
    return min(65536, max(width // 4, 0) * max((height - 4) // 3, 0))


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--client-jar', type=Path, default=Path(os.environ['APPDATA']) /
                        'PrismLauncher/libraries/com/mojang/minecraft/26.3/minecraft-26.3-client.jar')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    checked = []
    with ZipFile(args.client_jar) as jar:
        for stem in ('item', 'entity'):
            for stage in ('vsh', 'fsh'):
                rel = f'assets/minecraft/shaders/core/{stem}.{stage}'
                vanilla = jar.read(rel).decode('utf-8').replace('\r\n', '\n')
                shader = (args.root / rel).read_text(encoding='utf-8')
                assert shader == extract_core.transform(vanilla, stage), rel
                if stage == 'vsh':
                    assert 'vec4(pixel / ScreenSize * 2.0 - 1.0, 1.0, 1.0)' in shader, rel
                    assert '131072.0' not in shader, rel
                else:
                    header = shader.split('uint chromaHeaderWord(int word) {', 1)[1].split('\n}', 1)[0]
                    assert 'uint(chromaAutoCapacity(ivec2(ScreenSize)) - 1)' in header, rel
                    assert 'chromaSlot' not in header and 'chromaEye' not in header, rel
                    assert 'if (chromaReservedPixel()) discard;' in shader, rel
                checked.append(rel)
        rel = 'assets/minecraft/shaders/core/position_color.vsh'
        vanilla = jar.read(rel).decode('utf-8').replace('\r\n', '\n')
        shader = (args.root / rel).read_text(encoding='utf-8')
        assert shader == extract_core.transform_position_color(vanilla), rel
        # The fragment shader also serves debug_point. Preserve its exact native
        # vertex interface, color and projected XY; edit only matched depth.
        assert shader.split('void main() {')[0] == vanilla.split('void main() {')[0]
        assert shader.replace(extract_core.POSITION_COLOR_BRANCH, '') == vanilla
        assert 'abs(abs(Position) - vec3(0.3))' in shader
        assert 'Color.a > 0.999999' in shader
        assert 'abs(Color.rgb - vec3(Color.r))' in shader
        assert 'columnScale.x >= 0.1 - 0.000001' in shader
        assert 'abs(columnScale - vec3(columnScale.x))' in shader
        assert 'length(ModelViewMat[3].xyz)' not in shader
        assert 'gl_Position.z = gl_Position.w;' in shader
        checked.append(rel)
        rel = 'assets/minecraft/shaders/core/position_color.fsh'
        vanilla = jar.read(rel).decode('utf-8').replace('\r\n', '\n')
        shader = (args.root / rel).read_text(encoding='utf-8')
        assert shader == extract_core.transform_position_color(vanilla, 'fsh'), rel
        assert shader.replace(extract_core.POSITION_COLOR_FRAGMENT_BRANCH, '').replace(
            extract_core.POSITION_COLOR_FRAGMENT_INCLUDES, '') == vanilla
        assert 'gl_FragCoord.z == 1.0 && ProjMat[2][3] != 0.0' in shader
        assert 'chromaAutoHeaderPixel(pixel, size)' in shader
        assert 'chromaRawAddressAtPixel(pixel, size) >= 0' in shader
        checked.append(rel)
    assert not (args.root / 'assets/minecraft/shaders/core/terrain.fsh').exists()

    # The full scan must include the final packet at every supported resolution,
    # with neither its pixels nor any other packet touching the header row.
    resolutions = [(320, 240), (854, 480), (1920, 1080), (2560, 1440)]
    for width, height in resolutions:
        count = capacity(width, height)
        assert count > 0
        for address in range(count):
            x = 4 * (address % (width // 4))
            y = height - 4 - 3 * (address // (width // 4))
            assert 0 <= x and x + 3 < width and 0 <= y and y + 1 < height - 1
    result = {'generated_shaders_checked': checked,
              'terrain_override_required': False,
              'header_depth': 1.0,
              'header_bound': 'capacity - 1, identical for every writer',
              'resolutions': resolutions,
              'packet_pixel_bounds': 'pass',
              'client_gameplay': False,
              'fps_measured': False}
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
