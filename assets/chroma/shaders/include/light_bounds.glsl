#ifndef CHROMA_LIGHT_BOUNDS
#define CHROMA_LIGHT_BOUNDS
// Inclusive tile rectangle: four seven-bit coordinates + valid bit.
// RGBA8 transport keeps exact integer bounds without float render targets.
const ivec2 CHROMA_TILE_DIMS = ivec2(128, 72);
uint chromaBoundsRead(sampler2D source, int lamp) {
    uvec4 b = uvec4(texelFetch(source, ivec2(lamp, 0), 0) * 255.0 + 0.5);
    return b.x | (b.y << 8u) | (b.z << 16u) | (b.w << 24u);
}
ivec4 chromaBoundsRect(uint b) {
    return ivec4(int(b & 127u), int((b >> 7u) & 127u),
                 int((b >> 14u) & 127u), int((b >> 21u) & 127u));
}
vec4 chromaBoundsEncode(uint b) {
    return vec4(float(b & 255u), float((b >> 8u) & 255u),
                float((b >> 16u) & 255u), float((b >> 24u) & 255u)) / 255.0;
}
#endif
