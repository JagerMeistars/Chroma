#ifndef CHROMA_SHADOWS
#define CHROMA_SHADOWS
#include <chroma:voxel_space.glsl>

uniform sampler2D VoxelSampler;
uniform sampler2D VoxelLod1Sampler;
uniform sampler2D VoxelLod2Sampler;

bool chromaOccupiedLod(sampler2D volume, ivec3 absoluteCell, int level) {
#if CHROMA_STATIC_WORLD
    ivec3 cell = (absoluteCell - CHROMA_VOX_ORIGIN) >> level;
    int columns = (chromaVoxDims().x >> level) / 16;
#else
    int n = CHROMA_VOX_N >> level;
    ivec3 cell = (absoluteCell >> level) & (n - 1);
    int columns = n / 16;
#endif
    ivec2 pixel = ivec2(cell.x / 16 + columns * cell.z, cell.y);
    vec4 packed = texelFetch(volume, pixel, 0);
    uint channel = uint(packed[(cell.x & 15) >> 2] * 255.0 + 0.5);
    return ((channel >> uint((cell.x & 3) * 2)) & 3u) >= 2u;
}

float chromaVoxelExit(vec3 start, vec3 direction, float t, float size) {
    vec3 point = start + direction * t;
    vec3 boundary = (floor(point / size) + step(vec3(0.0), direction)) * size;
    vec3 crossing = mix((boundary - point) / direction, vec3(1e30),
                        lessThan(abs(direction), vec3(1e-7)));
    return t + max(min(crossing.x, min(crossing.y, crossing.z)), 0.0) + 0.0001;
}

float chromaTraceDistance(vec3 from, vec3 to) {
    // Coordinates stay relative to the camera until after subtraction, preserving
    // sub-block precision far from world zero. The occupancy lattice is world-fixed.
    ivec3 origin = chromaVoxOrigin();
    vec3 start = vec3(CameraBlockPos * CHROMA_VOX_CELLS - origin)
               + (from - CameraOffset) * float(CHROMA_VOX_CELLS);
    vec3 segment = (to - from) * float(CHROMA_VOX_CELLS);
    float lengthRay = length(segment);
    if (lengthRay < 0.001) return lengthRay * CHROMA_VOX_CELL;
    vec3 direction = segment / lengthRay;
    vec3 lo = vec3(0.0), hi = vec3(chromaVoxDims());
    vec3 inv = 1.0 / mix(direction, vec3(1e-20), lessThan(abs(direction), vec3(1e-20)));
    vec3 a = (lo - start) * inv, b = (hi - start) * inv;
    vec3 nearT = min(a, b), farT = max(a, b);
    float t = max(max(nearT.x, max(nearT.y, nearT.z)), 0.0) + 0.0001;
    float end = min(min(farT.x, min(farT.y, farT.z)), lengthRay - 0.001);
    // At most 3*256 cell crossings cover the dynamic cube. The safety budget
    // fails closed for unusually long, dense paths in larger static maps.
    for (int stepIndex = 0; stepIndex < CHROMA_SHADOW_STEPS; ++stepIndex) {
        if (t >= end) return lengthRay * CHROMA_VOX_CELL;
        ivec3 cell = origin + ivec3(floor(start + direction * t));
        if (!chromaVoxContains(cell, origin)) return lengthRay * CHROMA_VOX_CELL;
        if (!chromaOccupiedLod(VoxelLod2Sampler, cell, 2))
            t = chromaVoxelExit(start, direction, t, 4.0);
        else if (!chromaOccupiedLod(VoxelLod1Sampler, cell, 1))
            t = chromaVoxelExit(start, direction, t, 2.0);
        else if (!chromaOccupiedLod(VoxelSampler, cell, 0))
            t = chromaVoxelExit(start, direction, t, 1.0);
        else return t * CHROMA_VOX_CELL;
    }
    return min(t, lengthRay) * CHROMA_VOX_CELL;
}
#endif
