#ifndef CHROMA_BITS_GLSL
#define CHROMA_BITS_GLSL
// These operations survive Minecraft's SPIR-V -> desktop GLSL 330 translation.
// GLSL bitCount/findLSB are not enabled by that backend's generated source.
int chromaBitCount(uint value) {
    value -= (value >> 1u) & 0x55555555u;
    value = (value & 0x33333333u) + ((value >> 2u) & 0x33333333u);
    value = (value + (value >> 4u)) & 0x0F0F0F0Fu;
    return int((value * 0x01010101u) >> 24u);
}
int chromaFirstBit(uint value) {
    int result = 0;
    if ((value & 65535u) == 0u) { value >>= 16u; result += 16; }
    if ((value & 255u) == 0u) { value >>= 8u; result += 8; }
    if ((value & 15u) == 0u) { value >>= 4u; result += 4; }
    if ((value & 3u) == 0u) { value >>= 2u; result += 2; }
    if ((value & 1u) == 0u) result += 1;
    return result;
}
#endif
