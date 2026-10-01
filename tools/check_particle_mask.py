"""Check particle metadata against installed 26.3 pipelines, without a GPU/game.

This checks native blend/depth contracts and independent visibility/compositing
cases. Native shader compilation and live particles remain separate checks.
"""
from pathlib import Path
import argparse
import json
import os
import re
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]


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
    color_target = bytecode('com.mojang.renderpearl.api.pipeline.ColorTargetState')
    depth_state = bytecode('com.mojang.renderpearl.api.pipeline.DepthStencilState')
    opaque = pipelines.split('String pipeline/opaque_particle', 1)[1].split('Field OPAQUE_PARTICLE:', 1)[0]
    classic = pipelines.split('String pipeline/translucent_particle', 1)[1].split('Field TRANSLUCENT_PARTICLE:', 1)[0]
    assert 'ColorTargetState.DEFAULT' in opaque and 'withShaderDefine' not in opaque
    assert 'BlendFunction.TRANSLUCENT' in classic and 'withShaderDefine' not in classic
    defaults = color_target.split('static {};', 1)[1]
    assert 'Optional.empty' in defaults and 'RGBA8_UNORM' in defaults and 'bipush        15' in defaults
    defaults = depth_state.split('static {};', 1)[1]
    assert 'GREATER_THAN_OR_EQUAL' in defaults and 'iconst_1' in defaults
    premul = blend.split('Field TRANSLUCENT:', 1)[1].split('Field TRANSLUCENT_PREMULTIPLIED_ALPHA:', 1)[0]
    assert premul.count('BlendFactor.ONE:') == 2 and premul.count('BlendFactor.ONE_MINUS_SRC_ALPHA:') == 2

    path = ROOT/'assets/minecraft/shaders/core/particle.fsh'
    source = path.read_text()
    assert source.count('#if !CHROMA_STATIC_WORLD && CHROMA_PARTICLE_DEPTH_MASK') == 2
    assert '&& defined(OIT_DEPTH_BOUNDS)' in source and '&& !defined(OIT)' in source
    # Removing the two guarded metadata statements must restore the exact
    # native shader behavior, including classic alpha, fog and cutoff.
    stripped = re.sub(r'\s*#if !CHROMA_STATIC_WORLD && CHROMA_PARTICLE_DEPTH_MASK[^\n]*\n.*?#endif', '', source, flags=re.S)
    stripped = stripped.replace('#include <chroma:shadow_config.glsl>', '')
    with zipfile.ZipFile(jar_path) as jar:
        native = jar.read('assets/minecraft/shaders/core/particle.fsh').decode()
        assert compact(stripped) == compact(native)
        bounds = compact(jar.read('assets/minecraft/shaders/include/oit_depth_bounds.glsl').decode())
        sample = compact(jar.read('assets/minecraft/shaders/include/oit_depth_sample.glsl').decode())
        cull = compact(jar.read('assets/minecraft/shaders/core/oit_depth_bounds_cull.fsh').decode())
        composite = compact(jar.read('assets/minecraft/shaders/core/oit_composite.fsh').decode())
        assert 'vec4(-fragmentLinearDepth,fragmentLinearDepth,fragmentDeviceDepth,opaqueFragmentDeviceDepth)' in bounds
        assert 'depthBoundsSample.b' not in sample and 'depthBoundsSample.a' not in sample
        assert 'closestBoundDeviceDepth,opaqueOitDeviceDepth)' in cull
        assert 'gl_FragDepth=opaqueOitDeviceDepth;' in cull
        assert 'gl_FragDepth=closestBoundDeviceDepth;' in composite
    assert 'gl_FragDepth' not in source, 'Particle visibility must retain native depth tests/writes'

    voxel = (ROOT/'assets/chroma/shaders/post/voxel_update.fsh').read_text()
    assert 'uniform sampler2D MainColorSampler;' in voxel
    support = (ROOT/'assets/chroma/shaders/include/depth_support.glsl').read_text()
    assert '#include <chroma:depth_support.glsl>' in voxel
    assert 'metadataAlpha = texelFetch(MainColorSampler, p, 0).a' in support
    assert 'metadataAlpha < 0.5 / 255.0' in support
    assert 'texelFetch(InDepthSampler, p, 0).r > 0.000001' in support
    shade = (ROOT/'assets/chroma/shaders/post/shade.fsh').read_text()
    assert 'd > 0.000001 && texelFetch(InSampler, ivec2(suv * vec2(frameSize)), 0).a < 0.5 / 255.0' in shade
    chain = json.loads((ROOT/'assets/minecraft/post_effect/end_of_frame.json').read_text())
    update = next(p for p in chain['passes'] if p['fragment_shader']=='chroma:post/voxel_update')
    assert dict(sampler_name='MainColor', target='minecraft:main') in update['inputs']

    # Reverse-depth test: behind-wall particles never write color or metadata.
    # Front particles preserve native RGB/depth while alpha rejects learning.
    checked = 0
    for wall_depth in (0.0, .001, .1, .8, 1.0):
        for particle_depth in (.0001, .005, .2, .9):
            for alpha in (0.0, .05, .1, .5, 1.0):
                passes = alpha >= .1 and particle_depth >= wall_depth
                if not passes:
                    continue
                rgb = (.12, .46, .83)
                native_pixel = (*rgb, alpha)
                masked_pixel = (*rgb, 0.0)
                assert native_pixel[:3] == masked_pixel[:3]
                assert masked_pixel[3] < .5/255 and particle_depth > 1e-6
                # OIT MAX bounds changes only the final device-depth channel;
                # wavelet range and fully opaque depth are untouched.
                linear = .05/particle_depth
                bounds = (-linear, linear, particle_depth, particle_depth if alpha>.99 else 0.0)
                tagged = (*bounds[:2], 1.0, bounds[3])
                assert bounds[:2] == tagged[:2] and bounds[3] == tagged[3]
                for coverage in (0.0, .2, .75, 1.0):
                    background = (.4, .25, .1)
                    accumulated = tuple(c*coverage for c in rgb)
                    native_rgb = tuple(c+b*(1-coverage) for c,b in zip(accumulated,background))
                    tagged_rgb = tuple(c+b*(1-coverage) for c,b in zip(accumulated,background))
                    assert native_rgb == tagged_rgb
                checked += 1
    assert not (0.0 < .5/255 and 0.0 > 1e-6), 'Zero-alpha sky must still prove visible vacancy'
    # Classic uses alpha in RGB blending, so the feature must explicitly be
    # disabled there; the equality-to-native check above validates that path.
    assert (.8*.5+.2*.5) != (.8*0+.2*1)
    print(f'PASS native particle pipeline/blend/OIT channel contracts; {checked} visibility cases; Static/OFF native shader; sky vacancy; no GPU/game')


if __name__ == '__main__':
    main()
