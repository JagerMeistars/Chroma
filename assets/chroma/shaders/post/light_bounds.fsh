#version 450
#extension GL_ARB_separate_shader_objects : require
#include <chroma:lighting.glsl>
#include <chroma:shadow_config.glsl>
#include <chroma:light_bounds.glsl>
uniform sampler2D MatDecSampler;
uniform sampler2D SceneSampler;
layout(location = 1) flat in int cameraValid;
layout(location = 6) flat in mat4 cameraProj;
layout(location = 0) out vec4 fragColor;

void main() {
    fragColor = vec4(0.0);
    int k = int(gl_FragCoord.x);
    if (cameraValid == 0 || k >= CHROMA_LAMPS || !chromaMdLampOn(MatDecSampler, k)) return;
    float radius = max(chromaMdLampRadiusOf(MatDecSampler, k) * CHROMA_RADIUS_GAIN, 0.001);
#if CHROMA_SHADOW_PIXELATE
    radius += 1.25 / float(max(CHROMA_SHADOW_PIXELS_PER_BLOCK, 1));
#endif
    vec3 centre = chromaMdLampEyeOf(MatDecSampler, k);
    vec2 boundsMin = vec2(1.0e30), boundsMax = vec2(-1.0e30);
    bool full = false;
    for (int corner = 0; corner < 8; ++corner) {
        vec3 side = vec3((corner & 1) != 0 ? 1.0 : -1.0,
                         (corner & 2) != 0 ? 1.0 : -1.0,
                         (corner & 4) != 0 ? 1.0 : -1.0);
        vec4 clip = cameraProj * vec4(centre + side * radius, 1.0);
        if (clip.w <= 0.0001) { full = true; break; }
        vec2 uv = clip.xy / clip.w * 0.5 + 0.5;
        boundsMin = min(boundsMin, uv); boundsMax = max(boundsMax, uv);
    }
    ivec2 first = ivec2(0), last = CHROMA_TILE_DIMS - 1;
    if (!full) {
        vec2 grid = vec2(CHROMA_TILE_DIMS);
        vec2 margin = 2.0 / vec2(textureSize(SceneSampler, 0));
        // Binary searches use exactly the old tile-edge expressions, avoiding
        // ceil/floor rounding differences at touching light boundaries.
        ivec2 low = ivec2(0), high = CHROMA_TILE_DIMS;
        for (int i = 0; i < 8; ++i) {
            ivec2 mid = (low + high) / 2;
            vec2 edge = vec2(mid) / grid - margin + 1.0 / grid + 2.0 * margin;
            bvec2 before = bvec2(low.x < high.x && edge.x < boundsMin.x, low.y < high.y && edge.y < boundsMin.y);
            low = mix(low, mid + 1, before); high = mix(mid, high, before);
        }
        first = low;
        low = ivec2(0); high = CHROMA_TILE_DIMS;
        for (int i = 0; i < 8; ++i) {
            ivec2 mid = (low + high) / 2;
            vec2 edge = vec2(mid) / grid - margin;
            bvec2 inside = bvec2(low.x < high.x && edge.x <= boundsMax.x, low.y < high.y && edge.y <= boundsMax.y);
            low = mix(low, mid + 1, inside); high = mix(mid, high, inside);
        }
        last = min(low - 1, CHROMA_TILE_DIMS - 1);
        if (any(greaterThan(first, last))) return;
    }
    uint packed = uint(first.x) | (uint(first.y) << 7u) |
                  (uint(last.x) << 14u) | (uint(last.y) << 21u) | (1u << 28u);
    fragColor = chromaBoundsEncode(packed);
}
