#version 450
#extension GL_ARB_separate_shader_objects : require
#include <minecraft:globals.glsl>
#include <chroma:lighting.glsl>
#include <chroma:auto_read.glsl>
#include <chroma:voxel_space.glsl>
uniform sampler2D InDepthSampler;
#if !CHROMA_STATIC_WORLD && (CHROMA_PARTICLE_DEPTH_MASK || (CHROMA_ENTITY_SHADOWS != 1 && CHROMA_TRANSPARENT_DEPTH_MASK))
uniform sampler2D MainColorSampler;
#endif
uniform sampler2D CatalogSampler;
layout(location = 0) out vec4 fragColor;
#include <chroma:depth_support.glsl>

void main() {
    // Fixed-size table; ceil division covers arbitrary native resolutions.
    // Max reverse-Z bounds the nearest surface. Unknown pixels forbid a skip.
    ivec2 size = textureSize(InDepthSampler, 0);
    ivec2 tileSize = (size + ivec2(255)) / 256;
    ivec2 first = ivec2(gl_FragCoord.xy) * tileSize;
    ivec2 end = min(first + tileSize, size);
    float closest = 0.0;
    if (any(greaterThanEqual(first, size))) closest = 1.0;
    for (int y = first.y; y < end.y; ++y) {
        for (int x = first.x; x < end.x; ++x) {
            ivec2 p = ivec2(x, y);
            float depth = texelFetch(InDepthSampler, p, 0).r;
            if (!evidencePixel(p, size) || !(depth >= 0.0 && depth < 0.999999)) {
                fragColor = chromaVoxEncode(floatBitsToUint(1.0));
                return;
            }
            closest = max(closest, depth);
        }
    }
    fragColor = chromaVoxEncode(floatBitsToUint(closest));
}
