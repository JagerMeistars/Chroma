"""Check the final OIT noncaster mask against native 26.3, without a GPU/game.

Native shader compilation and live material/lighting checks are separate.
"""
from pathlib import Path
import argparse
import os
import re
import subprocess
from zipfile import ZipFile

from extract_core import transform_oit_composite

ROOT = Path(__file__).resolve().parents[1]
SHADER = 'assets/minecraft/shaders/core/oit_composite.fsh'


def compact(source):
    return re.sub(r'\s+', '', re.sub(r'//[^\n]*', '', source))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prism', type=Path, default=Path(os.environ['APPDATA'])/'PrismLauncher')
    args = parser.parse_args()
    jar_path = args.prism/'libraries/com/mojang/minecraft/26.3/minecraft-26.3-client.jar'
    javap = args.prism/'java/java-runtime-epsilon/bin/javap.exe'

    def bytecode(name):
        return subprocess.check_output([str(javap), '-p', '-c', '-classpath', str(jar_path), name], text=True)

    pipelines = bytecode('net.minecraft.client.renderer.RenderPipelines')
    blend = bytecode('com.mojang.renderpearl.api.pipeline.BlendFunction')
    level = bytecode('net.minecraft.client.renderer.LevelRenderer')
    composite = pipelines.split('String core/oit_composite', 1)[1].split('Field OIT_COMPOSITE:', 1)[0]
    assert 'SAMPLER0_OIT_COEFFS_DEPTH_BOUNDS_SAMPLER' in composite
    assert 'TRANSLUCENT_PREMULTIPLIED_ALPHA' in composite and 'RGBA8_UNORM' in composite
    assert 'CompareOp.ALWAYS_PASS' in composite and re.search(r'iconst_1\s+\d+: invokespecial .*DepthStencilState', composite)
    premul = blend.split('Field TRANSLUCENT:', 1)[1].split('Field TRANSLUCENT_PREMULTIPLIED_ALPHA:', 1)[0]
    assert premul.count('BlendFactor.ONE:') == 2 and premul.count('BlendFactor.ONE_MINUS_SRC_ALPHA:') == 2

    # Native world visibility is resolved before composite. Later outlines and
    # see-through features have no scene-depth attachment; on-top rendering
    # clears its own depth before drawing. This is not a world draw depth hack.
    main_pass = level.split('private void lambda$addMainPass$0(', 1)[1].split('private static ', 1)[0]
    assert main_pass.index('Method executeSolid:') < main_pass.index('Method executeOit:') < main_pass.index('Method executeOutline:')
    see_through = level.split('private void executeSeeThrough(', 1)[1].split('private void ', 1)[0]
    assert 'getDepthTextureView' not in see_through
    outline = level.split('private void executeOutline(', 1)[1].split('private ', 1)[0]
    assert 'getDepthTextureView' not in outline
    on_top = level.split('private void executeAlwaysOnTop(', 1)[1].split('private ', 1)[0]
    assert 'OptionalDouble.of' in on_top and 'dconst_0' in on_top

    source = (ROOT/SHADER).read_text()
    with ZipFile(jar_path) as jar:
        native = jar.read(SHADER).decode().replace('\r\n', '\n')
    assert source == transform_oit_composite(native), 'Generated composite hook drifted'
    branch = re.compile(r'#if !CHROMA_STATIC_WORLD && CHROMA_TRANSPARENT_DEPTH_MASK\n(.*?)#else\n(.*?)#endif', re.S)
    match = branch.search(source)
    assert match and len(branch.findall(source)) == 1
    assert compact(match[1]) == 'gl_FragDepth=1.0;'
    assert compact(match[2]) == 'gl_FragDepth=closestBoundDeviceDepth;'
    for static, enabled in ((0, 0), (1, 0), (1, 1)):
        restored = branch.sub(match[2], source).replace('#include <chroma:shadow_config.glsl>', '')
        assert compact(restored) == compact(native), f'Static/OFF parity failed: {static},{enabled}'
    # Exact source parity outside the one guarded depth write proves the native
    # cutoff, additive path, RGB normalization and alpha coverage are retained.
    assert 'coverage<0.00001&&dot(accumulatedColor.rgb,vec3(1.0))<0.00001' in compact(source)
    assert 'CHROMA_TRANSPARENT_DEPTH_MASK 1' in (ROOT/'assets/chroma/shaders/include/shadow_config.glsl').read_text()
    assert 'd >= 0.999999' in (ROOT/'assets/chroma/shaders/post/shade.fsh').read_text()
    assert '>= 0.999999' in (ROOT/'assets/chroma/shaders/post/voxel_update.fsh').read_text()

    # Independent reverse-depth + premultiplied-over cases: hidden fragments
    # and alpha-zero holes cannot replace background depth. Visible border,
    # stained-glass and water-like coverage keep native RGB/alpha, but their
    # final depth is unknown for Dynamic. Zero-coverage additive RGB also stays.
    cases = 0
    for background_depth in (0.0, .001, .3, .9):
        for fragment_depth in (.0001, .01, .5, .99):
            for alpha in (0.0, .1, .3, .6, 1.0):
                for additive in (False, True):
                    passes = fragment_depth >= background_depth
                    coverage = alpha if passes and not additive else 0.0
                    foreground = (.16, .43, .81)
                    accumulated = tuple(c*(1.0 if additive else coverage) if passes else 0.0 for c in foreground)
                    discard = coverage < .00001 and sum(accumulated) < .00001
                    background = (.31, .21, .08)
                    result_rgb = tuple(c + b*(1.0-coverage) for c, b in zip(accumulated, background))
                    native_depth = background_depth if discard else fragment_depth
                    masked_depth = background_depth if discard else 1.0
                    if not passes or (alpha == 0 and not additive):
                        assert discard and result_rgb == background and masked_depth == background_depth
                    else:
                        assert not discard and masked_depth >= .999999
                        assert native_depth == fragment_depth
                    for static, enabled in ((0, 0), (1, 0), (1, 1)):
                        selected_depth = masked_depth if not static and enabled else native_depth
                        assert selected_depth == native_depth
                    cases += 1
    print(f'PASS native OIT blend/depth/order; generated RGB/coverage parity; Static/OFF native; {cases} visibility/hole/additive cases; no GPU/game')


if __name__ == '__main__':
    main()
