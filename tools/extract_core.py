"""Rebuild Chroma core hooks from exact Minecraft 26.3 vanilla shaders.

Generated files retain GLSL 330 and vanilla branches. This writes item/entity
hooks, editor/screen-overlay guards and the final OIT depth mask; no terrain
or post shaders change.
"""
from argparse import ArgumentParser
from pathlib import Path
from zipfile import ZipFile
import os
VARYINGS = """
// Chroma's marker data. Locations 0..7 belong to the vanilla shaders.
layout(location = 8) {direction} float chromaMarker;
layout(location = 9) {direction} vec2 chromaUV;
layout(location = 10) {direction} vec4 chromaEye;
layout(location = 11) flat {direction} vec4 chromaColor;
layout(location = 12) flat {direction} int chromaShape;
layout(location = 13) flat {direction} vec3 chromaFacing;
layout(location = 14) flat {direction} int chromaSlot;
"""

VERTEX_HELPER = """
// Validate the complete marker code. Ordinary blue textures can share R/G,
// especially at an atlas corner whose padding repeats one texel five times.
bool chromaMatchSample(vec4 value, int identity) {
    int code = int(value.b * 255.0 + 0.5);
    return value.a >= 254.5 / 255.0 && (code & 192) == 0 &&
           (code & 7) <= 4 && (code & 39) == identity &&
           all(lessThan(abs(value.rg - vec2(76.0, 195.0) / 255.0), vec2(3.0 / 255.0)));
}
bool chromaMatchKey(vec2 uv, vec2 tx) {
    vec4 value = textureLod(Sampler0, uv, 0.0);
    int identity = int(value.b * 255.0 + 0.5) & 39; // Shape and header; corner varies.
    return chromaMatchSample(value, identity) &&
           chromaMatchSample(textureLod(Sampler0, uv + vec2(tx.x, 0.0), 0.0), identity) &&
           chromaMatchSample(textureLod(Sampler0, uv - vec2(tx.x, 0.0), 0.0), identity) &&
           chromaMatchSample(textureLod(Sampler0, uv + vec2(0.0, tx.y), 0.0), identity) &&
           chromaMatchSample(textureLod(Sampler0, uv - vec2(0.0, tx.y), 0.0), identity);
}
"""

VERTEX_BRANCH = """
    // Frame-local vertex addresses replace hand-assigned source slots.
    chromaMarker = 0.0;
    chromaUV = UV0;
    chromaEye = vec4(0.0, 0.0, 0.0, 1.0);
    chromaColor = vec4(Color.rgb, 1.0);
    chromaShape = 0;
    chromaFacing = vec3(0.0, 0.0, -1.0);
    chromaSlot = 0;
    vec2 chromaTexel = 1.0 / vec2(textureSize(Sampler0, 0));
    // Markers carry world-camera data; orthographic inventory/GUI stays native.
    if (ProjMat[2][3] != 0.0 && chromaMatchKey(UV0, chromaTexel)) {
        int variant = int(textureLod(Sampler0, UV0, 0.0).b * 255.0 + 0.5);
        int corner = (variant >> 3) & 3;
        bool header = (variant & 32) != 0;
        int quadFirst = gl_VertexIndex - corner;
        chromaSlot = quadFirst / 4 + (header ? 1 : 0);
        chromaMarker = header ? 2.0 : 1.0;
        chromaShape = variant & 7;
        chromaFacing = normalize((ModelViewMat * vec4(Normal, 0.0)).xyz);
        chromaEye = vec4((ModelViewMat * vec4(Position, 1.0)).xyz, 1.0);
        ivec2 size = ivec2(ScreenSize);
        ivec2 origin = header ? ivec2(0, size.y - 1) : chromaAutoOrigin(chromaSlot, size);
        vec2 extent = header ? vec2(32.0, 1.0) : vec2(4.0, 2.0);
        vec2 pixel = vec2(origin);
        if (corner == 0) pixel += vec2(0.0, extent.y);
        if (corner == 2) pixel += vec2(extent.x, 0.0);
        if (corner == 3) pixel += extent;
        // Reverse-depth near plane: terrain must not hide the camera packet.
        // Every header writer carries identical camera data and scan bounds.
        gl_Position = vec4(pixel / ScreenSize * 2.0 - 1.0, 1.0, 1.0);
        if (!header && (chromaSlot < 0 || chromaSlot >= chromaAutoCapacity(size)))
            gl_Position = vec4(2.0, 2.0, 1.0, 1.0);
    }
"""

FRAGMENT_HELPER = """
// Every marker writes the same current-camera header at the near plane.
// Scan the whole packet surface: draw order cannot select a source-address bound.
uint chromaHeaderWord(int word) {
    if (word == 0) return CHROMA_AUTO_HEADER;
    if (word <= 16) {
        int j = word - 1;
        return floatBitsToUint(ProjMat[j / 4][j % 4]);
    }
    if (word <= 25) {
        int j = word - 17;
        return floatBitsToUint(ModelViewMat[j / 3][j % 3]);
    }
    if (word == 26) return uint(chromaAutoCapacity(ivec2(ScreenSize)) - 1);
    return 0u;
}
vec4 chromaMarkerColor() {
    ivec2 size = ivec2(ScreenSize);
    ivec2 pixel = ivec2(gl_FragCoord.xy);
    if (chromaMarker > 1.5) {
        if (!chromaAutoHeaderPixel(pixel, size)) discard;
        int word = pixel.x;
        if (word == 27) {
            uint checksum = CHROMA_AUTO_CHECKSUM;
            for (int i = 0; i <= 26; ++i) checksum ^= chromaHeaderWord(i);
            return chromaAutoEncode(checksum);
        }
        return chromaAutoEncode(chromaHeaderWord(word));
    }
    // Derivatives restore the unchanged model geometry from its 4 by 2 raster.
    vec3 eye = chromaEye.xyz / chromaEye.w;
    vec3 dx = dFdx(eye) / dFdx(gl_FragCoord.x);
    vec3 dy = dFdy(eye) / dFdy(gl_FragCoord.y);
    vec2 uvDx = dFdx(chromaUV) / dFdx(gl_FragCoord.x);
    vec2 uvDy = dFdy(chromaUV) / dFdy(gl_FragCoord.y);
    bool uAlongX = abs(uvDx.x) > abs(uvDy.x);
    vec3 edgeU = uAlongX ? dx * 4.0 : dy * 2.0;
    vec3 edgeV = uAlongX ? dy * 2.0 : dx * 4.0;
    ivec2 origin = chromaAutoOrigin(chromaSlot, size);
    vec2 centrePixel = vec2(origin) + vec2(2.0, 1.0);
    vec3 centre = eye + dx * (centrePixel.x - gl_FragCoord.x)
                      + dy * (centrePixel.y - gl_FragCoord.y);
    ivec2 local = pixel - origin;
    if (chromaSlot < 0 || chromaSlot >= chromaAutoCapacity(size) ||
        local.x < 0 || local.x >= 4 || local.y < 0 || local.y >= 2) discard;
    uint words[8];
    words[0] = CHROMA_AUTO_SIGNATURE | uint(chromaShape);
    words[1] = floatBitsToUint(centre.x);
    words[2] = floatBitsToUint(centre.y);
    words[3] = floatBitsToUint(centre.z);
    words[4] = chromaAutoPackScales(length(edgeU), length(edgeV));
    words[5] = chromaAutoOctEncode(chromaFacing);
    words[6] = chromaAutoDecode(vec4(chromaColor.rgb, 1.0));
    words[7] = chromaAutoChecksum(words);
    return chromaAutoEncode(words[local.x + local.y * 4]);
}
"""

FRAGMENT_BRANCH = """
    if (chromaMarker > 0.5) {
        vec4 markerColor = chromaMarkerColor();
        #ifdef OIT_ALPHA_ONLY
        executeAlphaOnlyPhase(gl_FragCoord.z, markerColor.a);
        #elif defined(OIT_ACCUMULATE)
        fragColor = sampleColorForAccumulation(markerColor);
        #else
        fragColor = markerColor;
        #endif
        return;
    }
    // First-person items can clear scene depth before end_of_frame reads data.
    if (chromaReservedPixel()) discard;
"""

POSITION_COLOR_BRANCH = """
    if (chromaEditorGizmo(Position, Color, false))
        gl_Position.z = gl_Position.w; // Existing non-world/HUD depth sentinel.
"""

EDITOR_GIZMO_INCLUDE = '#include <chroma:editor_gizmo.glsl>\n'
LINES_BRANCH = POSITION_COLOR_BRANCH.replace('Color, false', 'Color, true')

POSITION_COLOR_FRAGMENT_INCLUDES = """#include <minecraft:globals.glsl>
#include <minecraft:projection.glsl>
#include <chroma:auto_read.glsl>
"""

POSITION_COLOR_FRAGMENT_BRANCH = """
    // Matched editor handles use depth 1, but Axiom's ALWAYS_PASS draw can
    // still overwrite Chroma's colour packets. Reserve transport pixels for
    // this overlay without changing the shared debug_point varying interface.
    if (gl_FragCoord.z == 1.0 && ProjMat[2][3] != 0.0) {
        ivec2 pixel = ivec2(gl_FragCoord.xy);
        ivec2 size = ivec2(ScreenSize);
        if (chromaAutoHeaderPixel(pixel, size) ||
            chromaRawAddressAtPixel(pixel, size) >= 0) discard;
    }
"""

SCREEN_OVERLAY_FRAGMENT_BRANCH = """
    // Vanilla block/water/fire screen effects use this shared shader after
    // world rendering. Preserve Chroma's packets only in their 3D-HUD pass;
    // ordinary orthographic GUI/startup draws keep the complete native image.
    // Reserving possible payload cells leaves gaps in a fullscreen overlay.
    if (ProjMat[2][3] != 0.0) {
        ivec2 pixel = ivec2(gl_FragCoord.xy);
        ivec2 size = ivec2(ScreenSize);
        if (chromaAutoHeaderPixel(pixel, size) ||
            chromaRawAddressAtPixel(pixel, size) >= 0) discard;
    }
"""


ENTITY_CASTER_BRANCH = """
    #if !CHROMA_STATIC_WORLD && CHROMA_ENTITY_SHADOWS != 1 && CHROMA_TRANSPARENT_DEPTH_MASK && !defined(OIT)
    // Improved Transparency ON routes blended entities through OIT. Only the
    // remaining opaque/cutout draw may use unused framebuffer alpha metadata.
    // Preserve native cutout, RGB, depth and all marker packets above. Mode 0/2
    // excludes this entity-shader group from persistent caster acquisition;
    // nonzero metadata still lets these surfaces receive Chroma lighting.
    if (fragColor.a >= 254.5 / 255.0) fragColor.a = 1.0 / 255.0;
    #endif
"""


def transform(vanilla: str, stage: str, *, entity_caster: bool = False) -> str:
    """Add Chroma hooks without editing the vanilla color/geometry branches."""
    if stage == 'vsh':
        anchor = '#include <minecraft:projection.glsl>\n'
        assert vanilla.count(anchor) == 1
        shader = vanilla.replace(anchor, anchor + '#include <minecraft:globals.glsl>\n#include <chroma:auto_transport.glsl>\n')
        before, after = shader.split('void main() {', 1)
        shader = before + 'uniform sampler2D Sampler0;\n' + VARYINGS.format(direction='out') + VERTEX_HELPER + '\nvoid main() {' + after
        end = shader.rfind('}')
        return shader[:end] + VERTEX_BRANCH + shader[end:]

    anchor = '#ifdef GLINT\n#include <minecraft:globals.glsl>\n#endif'
    assert vanilla.count(anchor) == 1
    shader = vanilla.replace(anchor, '#include <minecraft:globals.glsl>\n#include <minecraft:projection.glsl>\n#include <chroma:ferry_guard.glsl>')
    if entity_caster:
        shader = shader.replace('#include <chroma:ferry_guard.glsl>\n',
            '#include <chroma:ferry_guard.glsl>\n#include <chroma:shadow_config.glsl>\n')
        anchor = '    fragColor = calculateFinalColor(color);\n'
        assert shader.count(anchor) == 1
        shader = shader.replace(anchor, anchor + ENTITY_CASTER_BRANCH)
    before, after = shader.split('void main() {', 1)
    return before + VARYINGS.format(direction='in') + FRAGMENT_HELPER + '\nvoid main() {\n' + FRAGMENT_BRANCH + after


def transform_position_color(vanilla: str, stage: str = 'vsh') -> str:
    """Keep the native interface/color/XY and mark matched editor overlays."""
    if stage == 'fsh':
        anchor = '#include <minecraft:oit.glsl>\n'
        assert vanilla.count(anchor) == 1
        shader = vanilla.replace(anchor, anchor + POSITION_COLOR_FRAGMENT_INCLUDES)
        anchor = 'void main() {'
        assert shader.count(anchor) == 1
        return shader.replace(anchor, anchor + POSITION_COLOR_FRAGMENT_BRANCH)
    shader = vanilla.replace('#include <minecraft:projection.glsl>\n',
        '#include <minecraft:projection.glsl>\n' + EDITOR_GIZMO_INCLUDE)
    assert shader.count('vertexColor = Color;') == 1
    end = shader.rfind('}')
    return shader[:end] + POSITION_COLOR_BRANCH + shader[end:]


def transform_lines(vanilla: str, stage: str) -> str:
    if stage == 'fsh':
        return transform_position_color(vanilla, stage)
    return transform_position_color(vanilla).replace(POSITION_COLOR_BRANCH, LINES_BRANCH)


def write_position_color(jar: ZipFile, output: Path) -> None:
    for stage in ('vsh', 'fsh'):
        rel = f'assets/minecraft/shaders/core/position_color.{stage}'
        vanilla = jar.read(rel).decode('utf-8').replace('\r\n', '\n')
        destination = output / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(transform_position_color(vanilla, stage), encoding='utf-8', newline='\n')


def transform_screen_overlay(vanilla: str) -> str:
    """Protect packets from late perspective overlays, preserving native GUI."""
    anchor = '#extension GL_ARB_separate_shader_objects : require\n'
    assert vanilla.count(anchor) == 1
    shader = vanilla.replace(anchor, anchor + '\n' + POSITION_COLOR_FRAGMENT_INCLUDES)
    anchor = 'void main() {'
    assert shader.count(anchor) == 1
    return shader.replace(anchor, anchor + SCREEN_OVERLAY_FRAGMENT_BRANCH)


def write_screen_overlay(jar: ZipFile, output: Path) -> None:
    rel = 'assets/minecraft/shaders/core/position_tex_color.fsh'
    vanilla = jar.read(rel).decode('utf-8').replace('\r\n', '\n')
    destination = output / rel
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(transform_screen_overlay(vanilla), encoding='utf-8', newline='\n')


TRANSPARENT_DEPTH_BRANCH = """#if !CHROMA_STATIC_WORLD && CHROMA_TRANSPARENT_DEPTH_MASK
    // OIT has already resolved native visibility and premultiplied color.
    // Its nearest translucent depth is not opaque world geometry. Preserve
    // color/coverage and mark this pixel unknown to Dynamic's depth consumer.
    // Fully transparent holes were discarded above, retaining background depth.
    gl_FragDepth = 1.0;
    #else
    gl_FragDepth = closestBoundDeviceDepth;
    #endif"""


def transform_oit_composite(vanilla: str) -> str:
    """Change only final OIT depth; Static/OFF retains exact native behavior."""
    anchor = '#include <minecraft:oit.glsl>\n'
    assert vanilla.count(anchor) == 1
    shader = vanilla.replace(anchor, anchor + '#include <chroma:shadow_config.glsl>\n')
    anchor = 'gl_FragDepth = closestBoundDeviceDepth;'
    assert shader.count(anchor) == 1
    return shader.replace(anchor, TRANSPARENT_DEPTH_BRANCH)


def write_oit_composite(jar: ZipFile, output: Path) -> None:
    rel = 'assets/minecraft/shaders/core/oit_composite.fsh'
    vanilla = jar.read(rel).decode('utf-8').replace('\r\n', '\n')
    destination = output / rel
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(transform_oit_composite(vanilla), encoding='utf-8', newline='\n')


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--client-jar', type=Path, default=Path(os.environ['APPDATA']) / 'PrismLauncher/libraries/com/mojang/minecraft/26.3/minecraft-26.3-client.jar')
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    with ZipFile(args.client_jar) as jar:
        for stem in ['entity', 'item']:
            for stage in ['vsh', 'fsh']:
                rel = f'assets/minecraft/shaders/core/{stem}.{stage}'
                vanilla = jar.read(rel).decode('utf-8').replace('\r\n', '\n')
                destination = args.output / rel
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text(transform(vanilla, stage, entity_caster=stem == 'entity' and
                    (Path(__file__).resolve().parents[1] / 'assets/chroma/shaders/include/shadow_config.glsl').exists()),
                    encoding='utf-8', newline='\n')
                print(rel)
        write_position_color(jar, args.output)
        print('assets/minecraft/shaders/core/position_color.vsh')
        print('assets/minecraft/shaders/core/position_color.fsh')
        for stage in ('vsh', 'fsh'):
            rel = f'assets/minecraft/shaders/core/rendertype_lines.{stage}'
            shader = jar.read(rel).decode('utf-8').replace('\r\n', '\n')
            (args.output / rel).write_text(transform_lines(shader, stage), encoding='utf-8', newline='\n')
            print(rel)
        write_screen_overlay(jar, args.output)
        print('assets/minecraft/shaders/core/position_tex_color.fsh')
        write_oit_composite(jar, args.output)
        print('assets/minecraft/shaders/core/oit_composite.fsh')


if __name__ == '__main__':
    main()
