#version 450
#extension GL_ARB_separate_shader_objects : require

// Four texels per tile each hold the 32-bit union for one quarter of 128 lamps.
// Bounds include the entire light sphere and any snapped receiver displacement.
// Near-plane intersections conservatively touch
// every tile; no source is silently dropped when all 128 lights overlap.
#include <chroma:lighting.glsl>
#include <chroma:shadow_config.glsl>

uniform sampler2D MatDecSampler;
uniform sampler2D SceneSampler;
layout(location = 0) in vec2 texCoord;
layout(location = 1) flat in int cameraValid;
layout(location = 6) flat in mat4 cameraProj;
layout(location = 0) out vec4 fragColor;

#define CHROMA_TILE_GRID vec2(128.0, 72.0)

vec4 encodeMask(uint value) {
    return vec4(float(value & 255u), float((value >> 8) & 255u),
                float((value >> 16) & 255u), float((value >> 24) & 255u)) / 255.0;
}

bool lightTouchesTile(vec3 centre, float radius, vec2 tileMin, vec2 tileMax) {
    vec2 boundsMin = vec2(1.0e30);
    vec2 boundsMax = vec2(-1.0e30);
    for (int corner = 0; corner < 8; corner++) {
        vec3 side = vec3((corner & 1) != 0 ? 1.0 : -1.0,
                         (corner & 2) != 0 ? 1.0 : -1.0,
                         (corner & 4) != 0 ? 1.0 : -1.0);
        vec4 clip = cameraProj * vec4(centre + side * radius, 1.0);
        if (clip.w <= 0.0001) return true;
        vec2 uv = clip.xy / clip.w * 0.5 + 0.5;
        boundsMin = min(boundsMin, uv);
        boundsMax = max(boundsMax, uv);
    }
    return all(greaterThanEqual(boundsMax, tileMin))
        && all(lessThanEqual(boundsMin, tileMax));
}

void main() {
    if (cameraValid == 0) { fragColor = vec4(0.0); return; }
    int bank = int(gl_FragCoord.x) & 3;
    vec2 pixelMargin = 2.0 / vec2(textureSize(SceneSampler, 0));
    vec2 tileMin = floor(texCoord * CHROMA_TILE_GRID) / CHROMA_TILE_GRID - pixelMargin;
    vec2 tileMax = tileMin + 1.0 / CHROMA_TILE_GRID + 2.0 * pixelMargin;
    uint mask = 0u;
    for (int k = bank * 32; k < min((bank + 1) * 32, CHROMA_LAMPS); k++) {
        if (!chromaMdLampOn(MatDecSampler, k)) continue;
        float radius = max(chromaMdLampRadiusOf(MatDecSampler, k) * CHROMA_RADIUS_GAIN, 0.001);
#if CHROMA_SHADOW_PIXELATE
        // Two half-cell offsets plus the dominant-axis plane correction move
        // a sample by at most sqrt(1.5) cells. Do not clip a lit grid square.
        radius += 1.25 / float(max(CHROMA_SHADOW_PIXELS_PER_BLOCK, 1));
#endif
        if (lightTouchesTile(chromaMdLampEyeOf(MatDecSampler, k), radius, tileMin, tileMax))
            mask |= 1u << uint(k & 31);
    }
    fragColor = encodeMask(mask);
}
