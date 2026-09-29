#version 450
#extension GL_ARB_separate_shader_objects : require
#include <chroma:auto_read.glsl>
uniform sampler2D MainSampler;
layout(location = 0) out vec4 fragColor;
void main() {
    int first = int(gl_FragCoord.x) * 32;
    int capacity = chromaAutoCapacity(textureSize(MainSampler, 0));
    uint occupied = 0u;
    if (first >= capacity || chromaHeaderWord(MainSampler, 0) != CHROMA_AUTO_HEADER) {
        fragColor = chromaAutoEncode(0u); return;
    }
    int last = min(capacity - 1, int(chromaHeaderWord(MainSampler, 26)));
    if (first > last || !chromaHeaderValid(MainSampler)) {
        fragColor = chromaAutoEncode(0u); return;
    }
    for (int i = 0; i < 32 && first + i <= last; ++i)
        if (chromaRawValid(MainSampler, first + i)) occupied |= 1u << uint(i);
    fragColor = chromaAutoEncode(occupied);
}
