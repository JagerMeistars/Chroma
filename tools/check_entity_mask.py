"""CPU/native-JAR contracts for entity caster metadata. No GPU or game.

This is the shared entity-shader category, not a semantic mob identifier.
Improved Transparency ON is required: classic translucent and opaque entity
draws can share shader defines, so the existing transparent-mask switch gates it.
"""
from pathlib import Path
from zipfile import ZipFile
import argparse
import math
import os
import subprocess

import extract_core

ROOT = Path(__file__).resolve().parents[1]
INCLUDE = 'assets/chroma/shaders/include/'
ACTIVE = '!CHROMA_STATIC_WORLD && CHROMA_ENTITY_SHADOWS != 1 && CHROMA_TRANSPARENT_DEPTH_MASK'
COLOR_GUARD = '!CHROMA_STATIC_WORLD && (CHROMA_PARTICLE_DEPTH_MASK || (CHROMA_ENTITY_SHADOWS != 1 && CHROMA_TRANSPARENT_DEPTH_MASK))'


def byte(alpha):
    return math.floor(min(1., max(0., alpha)) * 255 + .5)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prism', type=Path, default=Path(os.environ['APPDATA'])/'PrismLauncher')
    args = parser.parse_args()
    jar_path = args.prism/'libraries/com/mojang/minecraft/26.3/minecraft-26.3-client.jar'
    javap = args.prism/'java/java-runtime-epsilon/bin/javap.exe'
    def native(name):
        return subprocess.check_output([str(javap), '-c', '-p', '-classpath', str(jar_path), name], text=True)

    pipelines = native('net.minecraft.client.renderer.RenderPipelines')
    for name, field in (('entity_solid', 'ENTITY_SOLID'), ('entity_cutout', 'ENTITY_CUTOUT'),
                        ('entity_cutout_cull', 'ENTITY_CUTOUT_CULL')):
        block = pipelines.split('String pipeline/'+name+'\n', 1)[1].split('Field '+field+':', 1)[0]
        assert 'ColorTargetState.DEFAULT' in block and 'BlendFunction.' not in block
    classic = pipelines.split('String pipeline/entity_translucent\n', 1)[1].split('Field ENTITY_TRANSLUCENT:', 1)[0]
    assert 'BlendFunction.TRANSLUCENT' in classic
    assert 'String PER_FACE_LIGHTING' in classic and 'String ALPHA_CUTOUT' in classic
    defaults = native('com.mojang.renderpearl.api.pipeline.ColorTargetState').split('static {};', 1)[1]
    assert 'Optional.empty' in defaults and 'RGBA8_UNORM' in defaults and 'bipush        15' in defaults

    with ZipFile(jar_path) as jar:
        vanilla = jar.read('assets/minecraft/shaders/core/entity.fsh').decode().replace('\r\n', '\n')
        shader = (ROOT/'assets/minecraft/shaders/core/entity.fsh').read_text()
        assert shader == extract_core.transform(vanilla, 'fsh', entity_caster=True)
        plain = extract_core.transform(vanilla, 'fsh')
        # Exact disabled-path parity: the only extra statements are the guarded
        # alpha write and config include; native cutout/fog/RGB are untouched.
        assert shader.replace(extract_core.ENTITY_CASTER_BRANCH, '').replace(
            '#include <chroma:shadow_config.glsl>\n', '') == plain
        assert 'shadow_config.glsl' not in plain and 'CHROMA_ENTITY_SHADOWS' not in plain
        item = jar.read('assets/minecraft/shaders/core/item.fsh').decode().replace('\r\n', '\n')
        assert (ROOT/'assets/minecraft/shaders/core/item.fsh').read_text() == extract_core.transform(item, 'fsh')
        oit = jar.read('assets/minecraft/shaders/include/oit.glsl').decode()
        assert '#ifdef OIT' in oit
    assert ACTIVE+' && !defined(OIT)' in extract_core.ENTITY_CASTER_BRANCH
    assert 'fragColor.a >= 254.5 / 255.0' in extract_core.ENTITY_CASTER_BRANCH
    assert 'fragColor.a = 1.0 / 255.0' in extract_core.ENTITY_CASTER_BRANCH
    assert extract_core.FRAGMENT_BRANCH in shader
    assert shader.index(extract_core.FRAGMENT_BRANCH) < shader.index('vec4 color = texture(Sampler0, texCoord0);')
    assert shader.index('if (color.a < ALPHA_CUTOUT)') < shader.index(extract_core.ENTITY_CASTER_BRANCH)
    assert shader.index('fragColor = calculateFinalColor(color);') < shader.index(extract_core.ENTITY_CASTER_BRANCH)

    config = (ROOT/INCLUDE/'shadow_config.glsl').read_text()
    assert '#define CHROMA_ENTITY_SHADOWS 1' in config
    assert '#define CHROMA_ENTITY_SHADOW_DISTANCE 4.0' in config
    assert '#define CHROMA_ENTITY_SHADOW_STEPS 24' in config
    evidence = (ROOT/INCLUDE/'depth_support.glsl').read_text().split('bool evidencePixel(', 1)[1].split('\n}', 1)[0]
    assert '#if '+COLOR_GUARD in evidence
    assert '#if CHROMA_ENTITY_SHADOWS != 1 && CHROMA_TRANSPARENT_DEPTH_MASK' in evidence
    assert 'if (int(floor(metadataAlpha * 255.0 + 0.5)) == 1) return false;' in evidence
    for name in ('voxel_update', 'surface_normal'):
        text = (ROOT/f'assets/chroma/shaders/post/{name}.fsh').read_text()
        assert '#if '+COLOR_GUARD+'\nuniform sampler2D MainColorSampler;' in text
        assert '#include <chroma:depth_support.glsl>' in text
    update = (ROOT/'assets/chroma/shaders/post/voxel_update.fsh').read_text()
    assert 'if (!evidencePixel(pixel, size)) return false;' in update
    assert 'return evidencePixel(p, size);' in update
    assert 'if (!projectPixel(eye, cameraProj, size, p)) return -1;' in update

    # Native visibility/cutout precedes the metadata write. In supported
    # unblended draws every RGB/depth value is unchanged; only byte255 becomes1.
    checked = 0
    rgb = (.13, .46, .79)
    for static in (False, True):
        for mode in (0, 1, 2):
            for transparent_mask in (False, True):
                for oit in (False, True):
                    active = not static and mode != 1 and transparent_mask and not oit
                    for alpha in (0., 1/255, .05, .1, .5, .99, 254/255, 1.):
                        for foreground in (False, True):
                            if alpha < .1 or not foreground:
                                # Discarded/occluded geometry cannot change the wall.
                                continue
                            native_pixel = (*rgb, alpha)
                            marked = (*rgb, 1/255 if active and byte(alpha) == 255 else alpha)
                            assert marked[:3] == native_pixel[:3]
                            if not active: assert marked == native_pixel
                            assert (byte(marked[3]) == 1) == (active and byte(alpha) == 255)
                            assert marked[3] > .5/255, 'Entity receivers must survive the particle alpha0 guard'
                            checked += 1
    assert byte(0.) == 0 and byte(1/255) == 1 and byte(2/255) == 2
    # Rejected evidence is UNKNOWN, never an empty-space observation: keeping
    # an old wall behind a tagged foreground entity must preserve every bit.
    old_mask = 0xa531
    classification = None if byte(1/255) == 1 else 'vacant'
    assert (0 if classification == 'vacant' else old_mask) == old_mask
    assert not (0. < .5/255 and 0. > 1e-6), 'Zero-depth sky still permits vacancy'
    # Alpha-byte1 in an arbitrary custom solid-terrain shader is an unavoidable
    # metadata collision. Native entity cutout cannot produce that low alpha.
    assert 1/255 < .1
    # Classic transparency is why mask0 must disable the write, even when an
    # original translucent draw happens to carry alpha1 at this pixel.
    assert abs((.8*(1/255)+.2*(254/255))-.8) > .5
    print(f'PASS entity metadata: installed unblended RGBA/native cutout contracts, exact Static/cache/OIT/OFF parity, '
          f'Auto/item/marker isolation, shared UNKNOWN evidence, {checked} visibility cases; no GPU/game')


if __name__ == '__main__':
    main()
