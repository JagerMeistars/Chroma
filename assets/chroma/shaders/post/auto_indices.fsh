#version 450
#extension GL_ARB_separate_shader_objects : require
#include <chroma:bits.glsl>
#include <chroma:auto_transport.glsl>
uniform sampler2D CatalogSampler;
uniform sampler2D CountsSampler;
layout(location = 0) out vec4 fragColor;
void main() {
    uint rank = uint(gl_FragCoord.x);
    int group = -1;
    for (int i = 0; i < 64; ++i) {
        uint count = chromaAutoDecode(texelFetch(CountsSampler, ivec2(i, 0), 0));
        if (rank < count) { group = i; break; }
        rank -= count;
    }
    if (group < 0) { fragColor = chromaAutoEncode(0u); return; }
    for (int i = 0; i < 32; ++i) {
        int block = group * 32 + i;
        uint occupied = chromaAutoDecode(texelFetch(CatalogSampler, ivec2(block, 0), 0));
        uint count = uint(chromaBitCount(occupied));
        if (rank < count) {
            for (uint j = 0u; j < rank; ++j) occupied &= occupied - 1u;
            fragColor = chromaAutoEncode(uint(block * 32 + chromaFirstBit(occupied) + 1)); return;
        }
        rank -= count;
    }
    fragColor = chromaAutoEncode(0u);
}
