#include <chroma:auto_transport.glsl>

uint chromaRawWord(sampler2D scene, int address, int word) {
    ivec2 origin = chromaAutoOrigin(address, textureSize(scene, 0));
    return chromaAutoDecode(texelFetch(scene, origin + ivec2(word & 3, word >> 2), 0));
}
uint chromaHeaderWord(sampler2D scene, int word) {
    return chromaAutoDecode(texelFetch(scene, ivec2(word, textureSize(scene, 0).y - 1), 0));
}
bool chromaHeaderValid(sampler2D scene) {
    if (chromaHeaderWord(scene, 0) != CHROMA_AUTO_HEADER) return false;
    uint checksum = CHROMA_AUTO_CHECKSUM;
    for (int i = 0; i < 27; ++i) checksum ^= chromaHeaderWord(scene, i);
    return checksum == chromaHeaderWord(scene, 27);
}
bool chromaRawValid(sampler2D scene, int address) {
    uint words[8];
    words[0] = chromaRawWord(scene, address, 0);
    if (!chromaAutoSignature(words[0])) return false;
    for (int i = 1; i < 8; ++i) words[i] = chromaRawWord(scene, address, i);
    vec3 position = vec3(uintBitsToFloat(words[1]), uintBitsToFloat(words[2]), uintBitsToFloat(words[3]));
    if (any(isnan(position)) || any(greaterThan(abs(position), vec3(1.0e6)))) return false;
    uint base = chromaAutoChecksumBase(words);
    ivec3 q = chromaAutoChecksumPosition(words);
    if (chromaAutoPositionChecksum(base, q) == words[7]) return true;
    // Adjacent fragment derivative groups can disagree by a few floating-point
    // bits. Accept neighbouring 1/1024 cells while retaining full float XYZ.
    for (int x = -1; x <= 1; ++x)
    for (int y = -1; y <= 1; ++y)
    for (int z = -1; z <= 1; ++z)
        if (chromaAutoPositionChecksum(base, q + ivec3(x,y,z)) == words[7]) return true;
    return false;
}
int chromaRawAddressAtPixel(ivec2 pixel, ivec2 size) {
    if (pixel.x < 0 || pixel.x >= chromaAutoColumns(size) * 4) return -1;
    int dy = size.y - 3 - pixel.y;
    if (dy < 0 || (dy % 3) > 1) return -1;
    int address = (dy / 3) * chromaAutoColumns(size) + pixel.x / 4;
    return address < chromaAutoCapacity(size) ? address : -1;
}
bool chromaCatalogHas(sampler2D catalog, int address) {
    if (address < 0) return false;
    uint occupied = chromaAutoDecode(texelFetch(catalog, ivec2(address >> 5, 0), 0));
    return (occupied & (1u << uint(address & 31))) != 0u;
}
