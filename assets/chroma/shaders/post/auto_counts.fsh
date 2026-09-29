#version 450
#extension GL_ARB_separate_shader_objects : require
#include <chroma:bits.glsl>
#include <chroma:auto_transport.glsl>
uniform sampler2D CatalogSampler;
layout(location = 0) out vec4 fragColor;
void main() {
    int first = int(gl_FragCoord.x) * 32;
    uint count = 0u;
    for (int i = 0; i < 32; ++i)
        count += uint(chromaBitCount(chromaAutoDecode(texelFetch(CatalogSampler, ivec2(first + i, 0), 0))));
    fragColor = chromaAutoEncode(count);
}
