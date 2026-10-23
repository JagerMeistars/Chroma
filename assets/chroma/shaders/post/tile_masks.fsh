#version 450
#extension GL_ARB_separate_shader_objects : require
#include <chroma:lighting.glsl>
#include <chroma:light_bounds.glsl>
uniform sampler2D LightBoundsSampler;
layout(location = 1) flat in int cameraValid;
layout(location = 0) out vec4 fragColor;
void main() {
    if (cameraValid == 0) { fragColor = vec4(0.0); return; }
    int bank = int(gl_FragCoord.x) & 3;
    ivec2 tile = ivec2(int(gl_FragCoord.x) / 4, int(gl_FragCoord.y));
    uint mask = 0u;
    for (int k = bank * 32; k < min((bank + 1) * 32, CHROMA_LAMPS); ++k) {
        uint packed = chromaBoundsRead(LightBoundsSampler, k);
        ivec4 r = chromaBoundsRect(packed);
        if ((packed & (1u << 28u)) != 0u &&
            all(greaterThanEqual(tile, r.xy)) && all(lessThanEqual(tile, r.zw)))
            mask |= 1u << uint(k & 31);
    }
    fragColor = chromaBoundsEncode(mask);
}
