#version 450
#extension GL_ARB_separate_shader_objects : require
#include <chroma:auto_read.glsl>
uniform sampler2D MainSampler;
uniform sampler2D IndicesSampler;
layout(location = 0) out vec4 fragColor;
void main() {
    uint encoded = chromaAutoDecode(texelFetch(IndicesSampler, ivec2(int(gl_FragCoord.x), 0), 0));
    fragColor = encoded == 0u ? vec4(0.0) : chromaAutoEncode(chromaRawWord(MainSampler, int(encoded - 1u), 6));
}
