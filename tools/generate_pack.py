"""Rebuild marker resources and native core hooks, preserving all post/lighting files.

Usage: python tools/generate_pack.py [--output PATH] [--client-jar PATH]
This never writes shade, tile masks, compaction, post-chain configuration or docs.
"""
from argparse import ArgumentParser
from pathlib import Path
from zipfile import ZipFile
import os
import extract_core
import generate_markers
ROOT=Path(__file__).resolve().parents[1]
TRANSPORT_INCLUDES = {'auto_transport.glsl': '#ifndef CHROMA_AUTO_TRANSPORT_GLSL\n#define CHROMA_AUTO_TRANSPORT_GLSL\nconst uint CHROMA_AUTO_SIGNATURE = 0xC7A03200u;\nconst uint CHROMA_AUTO_HEADER = 0xC7A04E01u;\nconst uint CHROMA_AUTO_CHECKSUM = 0x91E10DA5u;\nvec4 chromaAutoEncode(uint value) {\n    return vec4(float(value & 255u), float((value >> 8u) & 255u),\n                float((value >> 16u) & 255u), float(value >> 24u)) / 255.0;\n}\nuint chromaAutoDecode(vec4 rgba) {\n    uvec4 b = uvec4(clamp(rgba, 0.0, 1.0) * 255.0 + 0.5);\n    return b.r | (b.g << 8u) | (b.b << 16u) | (b.a << 24u);\n}\nint chromaAutoColumns(ivec2 size) { return max(size.x / 4, 1); }\nint chromaAutoCapacity(ivec2 size) {\n    return min(65536, max(size.x / 4, 0) * max((size.y - 4) / 3, 0));\n}\nivec2 chromaAutoOrigin(int address, ivec2 size) {\n    int columns = chromaAutoColumns(size);\n    return ivec2(4 * (address % columns), size.y - 4 - 3 * (address / columns));\n}\nbool chromaAutoHeaderPixel(ivec2 pixel, ivec2 size) {\n    return pixel.x >= 0 && pixel.x < 32 && pixel.y == size.y - 1;\n}\nbool chromaAutoSignature(uint word) {\n    return (word & 0xFFFFFFF8u) == CHROMA_AUTO_SIGNATURE && (word & 7u) <= 4u;\n}\n// Vertex interpolation can reconstruct the same centre a few ULPs apart in\n// different packet pixels. Keep its payload at full float32 precision, while\n// authenticating position at 1/1024-block precision. The reader may test the\n// 27 adjacent quantization cells; this is not a source-address hash.\nuint chromaAutoPositionChecksum(uint base, ivec3 q) {\n    return base ^ (uint(q.x) * 0x9E3779B1u)\n                ^ (uint(q.y) * 0x85EBCA77u)\n                ^ (uint(q.z) * 0xC2B2AE3Du);\n}\nuint chromaAutoChecksumBase(uint words[8]) {\n    return CHROMA_AUTO_CHECKSUM ^ words[0] ^ words[4] ^ words[5] ^ words[6];\n}\nivec3 chromaAutoChecksumPosition(uint words[8]) {\n    return ivec3(floor(vec3(uintBitsToFloat(words[1]),\n                           uintBitsToFloat(words[2]),\n                           uintBitsToFloat(words[3])) * 1024.0));\n}\nuint chromaAutoChecksum(uint words[8]) {\n    return chromaAutoPositionChecksum(chromaAutoChecksumBase(words),\n                                      chromaAutoChecksumPosition(words));\n}\nvec2 chromaAutoSign(vec2 v) {\n    return vec2(v.x >= 0.0 ? 1.0 : -1.0, v.y >= 0.0 ? 1.0 : -1.0);\n}\nuint chromaAutoOctEncode(vec3 normal) {\n    normal /= max(abs(normal.x) + abs(normal.y) + abs(normal.z), 0.000001);\n    vec2 p = normal.xy;\n    if (normal.z < 0.0) p = (1.0 - abs(p.yx)) * chromaAutoSign(p);\n    uvec2 q = uvec2(clamp(p * 0.5 + 0.5, 0.0, 1.0) * 65535.0 + 0.5);\n    return q.x | (q.y << 16u);\n}\nvec3 chromaAutoOctDecode(uint value) {\n    vec2 p = vec2(float(value & 65535u), float(value >> 16u)) / 65535.0 * 2.0 - 1.0;\n    vec3 n = vec3(p, 1.0 - abs(p.x) - abs(p.y));\n    if (n.z < 0.0) n.xy = (1.0 - abs(n.yx)) * chromaAutoSign(n.xy);\n    return normalize(n);\n}\nuint chromaAutoBFloat(float value) {\n    uint bits = floatBitsToUint(max(value, 0.0));\n    return (bits + 0x7FFFu + ((bits >> 16u) & 1u)) >> 16u;\n}\nuint chromaAutoPackScales(float radius, float intensity) {\n    return chromaAutoBFloat(radius) | (chromaAutoBFloat(intensity) << 16u);\n}\nvec2 chromaAutoUnpackScales(uint value) {\n    return vec2(uintBitsToFloat((value & 65535u) << 16u), uintBitsToFloat(value & 0xFFFF0000u));\n}\n#endif\n', 'ferry_guard.glsl': '// Only the shared camera header is protected from first-person depth clears.\n// Payload packets are validated and healed individually after scene rendering.\n#include <chroma:auto_transport.glsl>\nbool chromaReservedPixel() {\n    return ProjMat[2][3] != 0.0 &&\n        chromaAutoHeaderPixel(ivec2(gl_FragCoord.xy), ivec2(ScreenSize));\n}\n'}

def main():
    parser=ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT)
    parser.add_argument('--client-jar',type=Path,default=Path(os.environ['APPDATA'])/'PrismLauncher/libraries/com/mojang/minecraft/26.3/minecraft-26.3-client.jar')
    args=parser.parse_args()
    with ZipFile(args.client_jar) as jar:
        for name in ['entity','item']:
            for stage in ['vsh','fsh']:
                rel=f'assets/minecraft/shaders/core/{name}.{stage}'
                vanilla=jar.read(rel).decode('utf-8').replace('\r\n','\n')
                target=args.output/rel;target.parent.mkdir(parents=True,exist_ok=True)
                target.write_text(extract_core.transform(vanilla,stage),encoding='utf-8',newline='\n')
        extract_core.write_terrain(jar, args.output)
    for name,source in TRANSPORT_INCLUDES.items():
        target=args.output/f'assets/chroma/shaders/include/{name}';target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(source,encoding='utf-8',newline='\n')
    generate_markers.generate(args.output)

if __name__=='__main__':main()
