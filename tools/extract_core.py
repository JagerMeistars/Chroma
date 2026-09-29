"""Rebuild the four Chroma core hooks from exact Minecraft 26.3 vanilla shaders.

Generated files retain GLSL 330 and vanilla branches. This writes only item/entity
vertex and fragment shaders; it never changes post effects or appearance settings.
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
// R/G identify Chroma. B carries shape, local corner, and header/payload kind.
bool chromaMatchKey(vec2 uv, vec2 tx) {
    vec2 tolerance = vec2(3.0 / 255.0);
    vec2 key = vec2(76.0, 195.0) / 255.0;
    return all(lessThan(abs(textureLod(Sampler0, uv, 0.0).rg - key), tolerance)) &&
           all(lessThan(abs(textureLod(Sampler0, uv + vec2(tx.x, 0.0), 0.0).rg - key), tolerance)) &&
           all(lessThan(abs(textureLod(Sampler0, uv - vec2(tx.x, 0.0), 0.0).rg - key), tolerance)) &&
           all(lessThan(abs(textureLod(Sampler0, uv + vec2(0.0, tx.y), 0.0).rg - key), tolerance)) &&
           all(lessThan(abs(textureLod(Sampler0, uv - vec2(0.0, tx.y), 0.0).rg - key), tolerance));
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
    if (chromaMatchKey(UV0, chromaTexel)) {
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
        float depth = header ? 0.5 + float(min(chromaSlot, 65535)) / 131072.0 : 1.0;
        vec2 pixel = vec2(origin);
        if (corner == 0) pixel += vec2(0.0, extent.y);
        if (corner == 2) pixel += vec2(extent.x, 0.0);
        if (corner == 3) pixel += extent;
        gl_Position = vec4(pixel / ScreenSize * 2.0 - 1.0, depth, 1.0);
        if (!header && (chromaSlot < 0 || chromaSlot >= chromaAutoCapacity(size)))
            gl_Position = vec4(2.0, 2.0, 1.0, 1.0);
    }
"""

FRAGMENT_HELPER = """
// A shared header carries the current camera. Reverse depth arbitrates its
// writers: the marker with the highest automatic address wins all header words.
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
    if (word == 26) return uint(chromaSlot);
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


def transform(vanilla: str, stage: str) -> str:
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
    before, after = shader.split('void main() {', 1)
    return before + VARYINGS.format(direction='in') + FRAGMENT_HELPER + '\nvoid main() {\n' + FRAGMENT_BRANCH + after


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
                destination.write_text(transform(vanilla, stage), encoding='utf-8', newline='\n')
                print(rel)


if __name__ == '__main__':
    main()
