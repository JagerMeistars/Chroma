#version 450
#extension GL_ARB_separate_shader_objects : require
#include <minecraft:globals.glsl>
#include <chroma:lighting.glsl>
#include <chroma:shadows.glsl>

uniform sampler2D MatDecSampler;
uniform sampler2D PreviousShadowSampler;
uniform sampler2D CurrentShadowMetaSampler;
uniform sampler2D PreviousShadowMetaSampler;
uniform sampler2D VoxelMetaSampler;
layout(location = 0) out vec4 fragColor;

// Source-space radial distances: 128x128 octahedral maps, 16 columns x 8 rows.
// texelFetch consumers must fold octahedral seams before addressing a neighbour.
vec3 chromaShadowOctDecode(vec2 point) {
    vec3 direction = vec3(point, 1.0 - abs(point.x) - abs(point.y));
    if (direction.z < 0.0) {
        vec2 signs = vec2(direction.x >= 0.0 ? 1.0 : -1.0,
                          direction.y >= 0.0 ? 1.0 : -1.0);
        direction.xy = (1.0 - abs(direction.yx)) * signs;
    }
    return normalize(direction);
}

void main() {
    ivec2 pixel = ivec2(gl_FragCoord.xy);
    int lamp = pixel.x / 128 + (pixel.y / 128) * 16;
    int base = lamp * 8;
    if (lamp >= CHROMA_LAMPS
            || chromaVoxDecode(texelFetch(CurrentShadowMetaSampler, ivec2(base + 7, 0), 0)) != 1u) {
        fragColor = chromaVoxEncode(0u);
        return;
    }
    bool unchanged = true;
    for (int field = 0; field < 8; ++field) {
        uint current = chromaVoxDecode(texelFetch(CurrentShadowMetaSampler, ivec2(base + field, 0), 0));
        uint previous = chromaVoxDecode(texelFetch(PreviousShadowMetaSampler, ivec2(base + field, 0), 0));
        unchanged = unchanged && current == previous;
    }
#if !CHROMA_STATIC_WORLD
    // ponytail: observed-world geometry refreshes each source at least every
    // eight frames; moved/new sources bypass this bounded update delay.
    uint frame = chromaVoxDecode(texelFetch(VoxelMetaSampler, ivec2(4, 0), 0));
    unchanged = unchanged && ((frame + uint(lamp)) & 7u) != 0u;
#endif
    if (unchanged) {
        fragColor = texelFetch(PreviousShadowSampler, pixel, 0);
        return;
    }
    vec2 oct = (vec2(pixel & ivec2(127)) + 0.5) / 128.0 * 2.0 - 1.0;
    vec3 direction = chromaShadowOctDecode(oct);
    vec3 light = transpose(chromaMdRot(MatDecSampler, 0))
               * chromaMdLampEyeOf(MatDecSampler, lamp);
    float radius = uintBitsToFloat(chromaVoxDecode(texelFetch(CurrentShadowMetaSampler, ivec2(base + 6, 0), 0)));
    float distanceToBlocker = chromaTraceDistance(light, light + direction * radius);
    fragColor = chromaVoxEncode(floatBitsToUint(clamp(distanceToBlocker, 0.0, radius)));
}
