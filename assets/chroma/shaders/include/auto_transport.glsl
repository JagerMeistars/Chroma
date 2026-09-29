#ifndef CHROMA_AUTO_TRANSPORT_GLSL
#define CHROMA_AUTO_TRANSPORT_GLSL
const uint CHROMA_AUTO_SIGNATURE = 0xC7A03200u;
const uint CHROMA_AUTO_HEADER = 0xC7A04E01u;
const uint CHROMA_AUTO_CHECKSUM = 0x91E10DA5u;
vec4 chromaAutoEncode(uint value) {
    return vec4(float(value & 255u), float((value >> 8u) & 255u),
                float((value >> 16u) & 255u), float(value >> 24u)) / 255.0;
}
uint chromaAutoDecode(vec4 rgba) {
    uvec4 b = uvec4(clamp(rgba, 0.0, 1.0) * 255.0 + 0.5);
    return b.r | (b.g << 8u) | (b.b << 16u) | (b.a << 24u);
}
int chromaAutoColumns(ivec2 size) { return max(size.x / 4, 1); }
int chromaAutoCapacity(ivec2 size) {
    return min(65536, max(size.x / 4, 0) * max((size.y - 4) / 3, 0));
}
ivec2 chromaAutoOrigin(int address, ivec2 size) {
    int columns = chromaAutoColumns(size);
    return ivec2(4 * (address % columns), size.y - 4 - 3 * (address / columns));
}
bool chromaAutoHeaderPixel(ivec2 pixel, ivec2 size) {
    return pixel.x >= 0 && pixel.x < 32 && pixel.y == size.y - 1;
}
bool chromaAutoSignature(uint word) {
    return (word & 0xFFFFFFF8u) == CHROMA_AUTO_SIGNATURE && (word & 7u) <= 4u;
}
// Vertex interpolation can reconstruct the same centre a few ULPs apart in
// different packet pixels. Keep its payload at full float32 precision, while
// authenticating position at 1/1024-block precision. The reader may test the
// 27 adjacent quantization cells; this is not a source-address hash.
uint chromaAutoPositionChecksum(uint base, ivec3 q) {
    return base ^ (uint(q.x) * 0x9E3779B1u)
                ^ (uint(q.y) * 0x85EBCA77u)
                ^ (uint(q.z) * 0xC2B2AE3Du);
}
uint chromaAutoChecksumBase(uint words[8]) {
    return CHROMA_AUTO_CHECKSUM ^ words[0] ^ words[4] ^ words[5] ^ words[6];
}
ivec3 chromaAutoChecksumPosition(uint words[8]) {
    return ivec3(floor(vec3(uintBitsToFloat(words[1]),
                           uintBitsToFloat(words[2]),
                           uintBitsToFloat(words[3])) * 1024.0));
}
uint chromaAutoChecksum(uint words[8]) {
    return chromaAutoPositionChecksum(chromaAutoChecksumBase(words),
                                      chromaAutoChecksumPosition(words));
}
vec2 chromaAutoSign(vec2 v) {
    return vec2(v.x >= 0.0 ? 1.0 : -1.0, v.y >= 0.0 ? 1.0 : -1.0);
}
uint chromaAutoOctEncode(vec3 normal) {
    normal /= max(abs(normal.x) + abs(normal.y) + abs(normal.z), 0.000001);
    vec2 p = normal.xy;
    if (normal.z < 0.0) p = (1.0 - abs(p.yx)) * chromaAutoSign(p);
    uvec2 q = uvec2(clamp(p * 0.5 + 0.5, 0.0, 1.0) * 65535.0 + 0.5);
    return q.x | (q.y << 16u);
}
vec3 chromaAutoOctDecode(uint value) {
    vec2 p = vec2(float(value & 65535u), float(value >> 16u)) / 65535.0 * 2.0 - 1.0;
    vec3 n = vec3(p, 1.0 - abs(p.x) - abs(p.y));
    if (n.z < 0.0) n.xy = (1.0 - abs(n.yx)) * chromaAutoSign(n.xy);
    return normalize(n);
}
uint chromaAutoBFloat(float value) {
    uint bits = floatBitsToUint(max(value, 0.0));
    return (bits + 0x7FFFu + ((bits >> 16u) & 1u)) >> 16u;
}
uint chromaAutoPackScales(float radius, float intensity) {
    return chromaAutoBFloat(radius) | (chromaAutoBFloat(intensity) << 16u);
}
vec2 chromaAutoUnpackScales(uint value) {
    return vec2(uintBitsToFloat((value & 65535u) << 16u), uintBitsToFloat(value & 0xFFFF0000u));
}
#endif
