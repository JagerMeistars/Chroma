#version 450
#extension GL_ARB_separate_shader_objects : require
#include <minecraft:globals.glsl>
#include <chroma:lighting.glsl>
#include <chroma:voxel_space.glsl>

uniform sampler2D ShadowSampler;
uniform sampler2D MatDecSampler;
uniform sampler2D CurrentShadowMetaSampler;
uniform sampler2D PreviousShadowMetaSampler;
uniform sampler2D VoxelMetaSampler;
uniform sampler2D VoxelSampler;
uniform sampler2D VoxelLod1Sampler;
layout(location = 0) out vec4 fragColor;

// One payload per radial shadow-map texel. Bits 0..29 retain the finite
// surface record; bit 30 selects the cell AFTER the hit (otherwise BEFORE).
// Bit 31 retains the full-cell overflow flag. A nonzero mask or overflow
// denotes a valid payload; consumers restore the record's normal valid bit.
// The target persists in place. Its refresh predicate must match shadow_map.
vec3 chromaSurfaceDirection(ivec2 pixel) {
    vec2 oct = (vec2(pixel & ivec2(127)) + 0.5) / 128.0 * 2.0 - 1.0;
    vec3 direction = vec3(oct, 1.0 - abs(oct.x) - abs(oct.y));
    if (direction.z < 0.0) {
        vec2 signs = vec2(direction.x >= 0.0 ? 1.0 : -1.0,
                          direction.y >= 0.0 ? 1.0 : -1.0);
        direction.xy = (1.0 - abs(direction.yx)) * signs;
    }
    return normalize(direction);
}

uint chromaSurfacePayload(vec3 light, vec3 direction, float depth) {
    vec3 hit = light + direction * depth;
    ivec3 before = chromaVoxOf(light + direction * (depth - 0.0001));
    ivec3 after = chromaVoxOf(light + direction * (depth + 0.0001));
    uint payload = 0u;
    float best = 0.001;
    for (int side = 0; side < 2; ++side) {
        ivec3 cell = side == 0 ? before : after;
        if (side == 1 && all(equal(before, after))) continue;
        if (!chromaVoxContains(cell, chromaVoxOrigin())
                || !chromaOccupiedLod(VoxelLod1Sampler, cell, 1)) continue;
        uvec4 data = chromaVoxSurfaceData(VoxelSampler, cell);
        uint owner = side == 0 ? 0u : 0x40000000u;
        if (((data.x | data.y | data.z | data.w) & 0x80000000u) != 0u) {
            float boxDepth;
            vec3 low = chromaVoxLower(cell);
            if (chromaVoxBoxRayHit(low, low + CHROMA_VOX_CELL, light,
                    direction, depth + 0.001, boxDepth)
                    && abs(boxDepth - depth) < 0.001)
                return 0x80000000u | owner;
            continue;
        }
        for (int slot = 0; slot < CHROMA_VOX_SURFACES; ++slot) {
            uint record = data[slot];
            if (!chromaSurfelValid(record) || chromaSurfelMask(record) == 0u) continue;
            vec3 normal = chromaSurfelNormal(record);
            float offset = (float((record >> 8u) & 63u) / 63.0 - 0.5)
                         * CHROMA_VOX_CELL * dot(abs(normal), vec3(1.0));
            vec3 point = chromaVoxCentre(cell) + normal * offset;
            float error = abs(dot(normal, hit - point));
            if (error <= best && chromaSurfelCoveredAxis(record, cell, hit,
                                                        chromaSurfelAxis(normal))) {
                best = error;
                payload = (record & 0x3fffffffu) | owner;
            }
        }
    }
    return payload;
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
    uint frame = chromaVoxDecode(texelFetch(VoxelMetaSampler, ivec2(4, 0), 0));
    unchanged = unchanged && ((frame + uint(lamp)) & 7u) != 0u;
    if (unchanged) discard;

    float depth = uintBitsToFloat(chromaVoxDecode(texelFetch(ShadowSampler, pixel, 0)));
    float radius = uintBitsToFloat(chromaVoxDecode(texelFetch(CurrentShadowMetaSampler, ivec2(base + 6, 0), 0)));
    if (depth <= 0.0001 || depth >= radius - 0.001) {
        fragColor = chromaVoxEncode(0u);
        return;
    }
    vec3 light = transpose(chromaMdRot(MatDecSampler, 0))
               * chromaMdLampEyeOf(MatDecSampler, lamp);
    light = chromaShadowMapOrigin(light);
    fragColor = chromaVoxEncode(chromaSurfacePayload(light, chromaSurfaceDirection(pixel), depth));
}
