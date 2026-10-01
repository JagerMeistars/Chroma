#ifndef CHROMA_VOXEL_SPACE
#define CHROMA_VOXEL_SPACE
// The caller includes minecraft:globals.glsl before this file.
#include <chroma:shadow_config.glsl>
#define CHROMA_VOX_CELLS 4
#define CHROMA_VOX_N 256
#define CHROMA_VOX_CELL 0.25
#define CHROMA_VOX_PUSH (CHROMA_VOX_CELL * 0.08)
#define CHROMA_VOX_SURFACES 4
#define CHROMA_VOX_META_MAGIC 0xC70A0256u
#ifndef CHROMA_VOX_UPDATE_PHASES
#define CHROMA_VOX_UPDATE_PHASES (CHROMA_VOX_CELLS * 2)
#endif

bool chromaVoxUpdateSlice(ivec3 voxel, uint frame) {
    // Keep adjacent X records in the same update phase: mixed active lanes
    // still execute the expensive acquisition on the whole GPU group.
    int phase = voxel.y ^ (voxel.z >> 3);
    return (phase % CHROMA_VOX_UPDATE_PHASES + CHROMA_VOX_UPDATE_PHASES)
        % CHROMA_VOX_UPDATE_PHASES == int(frame % uint(CHROMA_VOX_UPDATE_PHASES));
}

uint chromaVoxDecode(vec4 value) {
    uvec4 b = uvec4(value * 255.0 + 0.5);
    return b.r | (b.g << 8u) | (b.b << 16u) | (b.a << 24u);
}
vec4 chromaVoxEncode(uint value) {
    return vec4(value & 255u, (value >> 8u) & 255u,
                (value >> 16u) & 255u, value >> 24u) / 255.0;
}
// Match shadow_meta's source identity exactly. Retained radial depth and its
// finite-surface payload must reconstruct cells from the same map origin.
vec3 chromaShadowMapOrigin(vec3 light) {
    vec3 relative = light - CameraOffset;
    vec3 whole = floor(relative);
    return whole + floor((relative - whole) * 4096.0 + 0.5) / 4096.0 + CameraOffset;
}
ivec3 chromaVoxDims() {
#if CHROMA_STATIC_WORLD
    return CHROMA_VOX_DIMS;
#else
    return ivec3(CHROMA_VOX_N);
#endif
}
ivec3 chromaVoxOrigin() {
#if CHROMA_STATIC_WORLD
    return CHROMA_VOX_ORIGIN;
#else
    return (CameraBlockPos + ivec3(floor(-CameraOffset))) * CHROMA_VOX_CELLS
        - ivec3(CHROMA_VOX_N / 2);
#endif
}
bool chromaVoxContains(ivec3 voxel, ivec3 origin) {
    ivec3 local = voxel - origin;
    return all(greaterThanEqual(local, ivec3(0))) && all(lessThan(local, chromaVoxDims()));
}
ivec3 chromaVoxOf(vec3 cameraRelativeWorld) {
    return CameraBlockPos * CHROMA_VOX_CELLS
        + ivec3(floor((cameraRelativeWorld - CameraOffset) * float(CHROMA_VOX_CELLS)));
}
vec3 chromaVoxCentre(ivec3 voxel) {
    return (vec3(voxel - CameraBlockPos * CHROMA_VOX_CELLS) + 0.5) * CHROMA_VOX_CELL
        + CameraOffset;
}
ivec3 chromaVoxStorage(ivec3 voxel) {
#if CHROMA_STATIC_WORLD
    return voxel - CHROMA_VOX_ORIGIN;
#else
    return voxel & (CHROMA_VOX_N - 1);
#endif
}
ivec2 chromaVoxTexel(ivec3 voxel) {
    ivec3 v = chromaVoxStorage(voxel);
#if CHROMA_STATIC_WORLD
    return ivec2(v.x / 16 + (chromaVoxDims().x / 16) * v.z, v.y);
#else
    int index = CHROMA_VOX_SURFACES * (v.x + CHROMA_VOX_N * (v.y + CHROMA_VOX_N * v.z));
    return ivec2(index & 4095, index >> 12);
#endif
}
uint chromaVoxShift(ivec3 voxel) {
#if CHROMA_STATIC_WORLD
    return uint((chromaVoxStorage(voxel).x & 15) * 2);
#else
    return 0u;
#endif
}
// Static files keep their original sixteen two-bit cells per RGBA texel.
// Dynamic cells own four surface records, adjacent in a 4096 x 16384 texture.
ivec2 chromaVoxSurfaceTexel(ivec3 voxel, int slot) {
    ivec2 pixel = chromaVoxTexel(voxel);
    return pixel + ivec2(slot, 0); // Four-aligned groups never cross a texture row.
}
uint chromaVoxData(sampler2D volume, ivec3 voxel) {
    if (!chromaVoxContains(voxel, chromaVoxOrigin())) return 0u;
#if CHROMA_STATIC_WORLD
    return (chromaVoxDecode(texelFetch(volume, chromaVoxTexel(voxel), 0))
            >> chromaVoxShift(voxel)) & 3u;
#else
    return chromaVoxDecode(texelFetch(volume, chromaVoxTexel(voxel), 0));
#endif
}
uvec4 chromaVoxSurfaceData(sampler2D volume, ivec3 voxel) {
    if (!chromaVoxContains(voxel, chromaVoxOrigin())) return uvec4(0u);
#if CHROMA_STATIC_WORLD
    return uvec4(chromaVoxData(volume, voxel), 0u, 0u, 0u);
#else
    return uvec4(chromaVoxDecode(texelFetch(volume, chromaVoxSurfaceTexel(voxel, 0), 0)),
                 chromaVoxDecode(texelFetch(volume, chromaVoxSurfaceTexel(voxel, 1), 0)),
                 chromaVoxDecode(texelFetch(volume, chromaVoxSurfaceTexel(voxel, 2), 0)),
                 chromaVoxDecode(texelFetch(volume, chromaVoxSurfaceTexel(voxel, 3), 0)));
#endif
}
bool chromaSurfelValid(uint data) { return (data & 0x40000000u) != 0u; }
uint chromaSurfelMask(uint data) { return (data >> 14u) & 65535u; }
uint chromaVoxConfidence(sampler2D volume, ivec3 voxel) {
#if CHROMA_STATIC_WORLD
    return chromaVoxData(volume, voxel) & 3u;
#else
    uvec4 data = chromaVoxSurfaceData(volume, voxel);
    if (((data.x | data.y | data.z | data.w) & 0x80000000u) != 0u) return 3u;
    for (int slot = 0; slot < CHROMA_VOX_SURFACES; ++slot)
        if (chromaSurfelValid(data[slot]) && chromaSurfelMask(data[slot]) != 0u) return 3u;
    return 0u;
#endif
}
vec3 chromaVoxLower(ivec3 voxel) {
    // Subtract integers first: conversion of absolute world positions to float
    // would lose the sub-block bounds near the world border.
    return vec3(voxel - CameraBlockPos * CHROMA_VOX_CELLS) * CHROMA_VOX_CELL
        + CameraOffset;
}
vec3 chromaSurfelNormal(uint data) {
    // Fifteen levels include zero exactly; sixteen would tilt every axis face.
    vec2 oct = vec2(data & 15u, (data >> 4u) & 15u) / 14.0 * 2.0 - 1.0;
    vec3 normal = vec3(oct, 1.0 - abs(oct.x) - abs(oct.y));
    if (normal.z < 0.0)
        normal.xy = (1.0 - abs(normal.yx))
                  * mix(vec2(-1.0), vec2(1.0), greaterThanEqual(normal.xy, vec2(0.0)));
    return normalize(normal);
}
int chromaSurfelAxis(vec3 normal) {
    vec3 a = abs(normal);
    return a.x >= max(a.y, a.z) ? 0 : (a.y >= a.z ? 1 : 2);
}
vec3 chromaSurfelPoint(uint data, ivec3 voxel) {
    vec3 normal = chromaSurfelNormal(data);
    float offset = (float((data >> 8u) & 63u) / 63.0 - 0.5)
                 * CHROMA_VOX_CELL * dot(abs(normal), vec3(1.0));
    return chromaVoxCentre(voxel) + normal * offset;
}
uint chromaSurfelEncode(vec3 hit, vec3 normal, ivec3 voxel, uint mask) {
    if (dot(normal, normal) < 0.5) return 0u;
    normal = normalize(normal);
    vec3 cellCenter = chromaVoxCentre(voxel);
    // Rotate the quantized plane around the same center-based anchor, rather
    // than around whichever point this camera happened to observe on it.
    vec3 anchor = cellCenter + normal * dot(normal, hit - cellCenter);
    normal /= abs(normal.x) + abs(normal.y) + abs(normal.z);
    vec2 oct = normal.xy;
    if (normal.z < 0.0)
        oct = (1.0 - abs(oct.yx))
            * mix(vec2(-1.0), vec2(1.0), greaterThanEqual(oct, vec2(0.0)));
    uvec2 encoded = uvec2(clamp(floor((oct * 0.5 + 0.5) * 14.0 + 0.5), 0.0, 14.0));
    uint word = encoded.x | (encoded.y << 4u);
    vec3 storedNormal = chromaSurfelNormal(word);
    float level = dot(storedNormal, anchor - cellCenter)
                / (CHROMA_VOX_CELL * dot(abs(storedNormal), vec3(1.0))) + 0.5;
    uint plane = uint(clamp(floor(level * 63.0 + 0.5), 0.0, 63.0));
    return word | (plane << 8u) | ((mask & 65535u) << 14u) | 0x40000000u;
}
bool chromaSurfelCoveredAxis(uint data, ivec3 voxel, vec3 point, int axis) {
    vec3 local = (point - chromaVoxLower(voxel)) / CHROMA_VOX_CELL;
    if (any(lessThan(local, vec3(-0.00004))) || any(greaterThan(local, vec3(1.00004)))) return false;
    ivec2 patchCoord = clamp(ivec2(floor(vec2(local[(axis + 1) % 3], local[(axis + 2) % 3]) * 4.0)),
                        ivec2(0), ivec2(3));
    return ((chromaSurfelMask(data) >> uint(patchCoord.x + patchCoord.y * 4)) & 1u) != 0u;
}
bool chromaSurfelCovered(uint data, ivec3 voxel, vec3 point) {
    return chromaSurfelCoveredAxis(data, voxel, point, chromaSurfelAxis(chromaSurfelNormal(data)));
}
bool chromaVoxPointOccupied(sampler2D volume, vec3 point) {
    ivec3 voxel = chromaVoxOf(point);
    uvec4 data = chromaVoxSurfaceData(volume, voxel);
#if CHROMA_STATIC_WORLD
    return (data.x & 3u) >= 2u;
#else
    if (((data.x | data.y | data.z | data.w) & 0x80000000u) != 0u) return true;
    for (int slot = 0; slot < CHROMA_VOX_SURFACES; ++slot)
        if (chromaSurfelValid(data[slot]) && chromaSurfelCovered(data[slot], voxel, point)
            && abs(dot(chromaSurfelNormal(data[slot]), point - chromaSurfelPoint(data[slot], voxel))) < 0.00001)
            return true;
    return false;
#endif
}
// A positive-length intersection with a half-open box. Parallel rays exactly on
// its upper face do not enter the cell; tangencies must not fill alpha holes.
bool chromaVoxBoxRayHit(vec3 lower, vec3 upper, vec3 rayOrigin, vec3 direction,
                      float maxDistance, out float distance) {
    float enter = 0.0, leave = maxDistance;
    distance = maxDistance;
    if (maxDistance <= 0.0 || any(greaterThanEqual(lower, upper))) return false;
    for (int axis = 0; axis < 3; ++axis) {
        if (abs(direction[axis]) < 1e-8) {
            if (rayOrigin[axis] < lower[axis] || rayOrigin[axis] >= upper[axis]) return false;
        } else {
            float a = (lower[axis] - rayOrigin[axis]) / direction[axis];
            float b = (upper[axis] - rayOrigin[axis]) / direction[axis];
            enter = max(enter, min(a, b));
            leave = min(leave, max(a, b));
        }
    }
    if (leave <= enter) return false;
    distance = enter;
    return true;
}
bool chromaVoxDataRayHit(uvec4 data, ivec3 voxel, vec3 rayOrigin, vec3 direction,
                       float maxDistance, out float distance) {
    distance = maxDistance;
    if (maxDistance <= 0.0) return false;
#if CHROMA_STATIC_WORLD
    if ((data.x & 3u) < 2u) return false;
    vec3 lower = chromaVoxLower(voxel);
    return chromaVoxBoxRayHit(lower, lower + CHROMA_VOX_CELL, rayOrigin, direction, maxDistance, distance);
#else
    if (((data.x | data.y | data.z | data.w) & 0x80000000u) != 0u) {
        vec3 lower = chromaVoxLower(voxel);
        return chromaVoxBoxRayHit(lower, lower + CHROMA_VOX_CELL, rayOrigin, direction, maxDistance, distance);
    }
    bool found = false;
    for (int slot = 0; slot < CHROMA_VOX_SURFACES; ++slot) {
        uint surface = data[slot];
        if (!chromaSurfelValid(surface) || chromaSurfelMask(surface) == 0u) continue;
        vec3 normal = chromaSurfelNormal(surface);
        int axis = chromaSurfelAxis(normal);
        float offset = (float((surface >> 8u) & 63u) / 63.0 - 0.5)
                     * CHROMA_VOX_CELL * dot(abs(normal), vec3(1.0));
        float height = dot(normal, chromaVoxCentre(voxel) - rayOrigin) + offset;
        float denominator = dot(normal, direction);
        if (abs(denominator) < 0.0000001) {
            if (abs(height) < 0.00001 && chromaSurfelCoveredAxis(surface, voxel, rayOrigin, axis)) {
                distance = 0.0; return true;
            }
            continue;
        }
        float hit = height / denominator;
        if (hit >= 0.0 && hit < distance
            && chromaSurfelCoveredAxis(surface, voxel, rayOrigin + direction * hit, axis)) {
            distance = hit; found = true;
        }
    }
    return found;
#endif
}
bool chromaVoxRayHit(sampler2D volume, ivec3 voxel, vec3 rayOrigin, vec3 direction,
                   float maxDistance, out float distance) {
    return chromaVoxDataRayHit(chromaVoxSurfaceData(volume, voxel), voxel,
                             rayOrigin, direction, maxDistance, distance);
}
// Visibility only needs a hit, while shadow-map construction needs the nearest
// distance. Keep its nearest-hit path above unchanged.
bool chromaVoxDataRayAny(uvec4 data, ivec3 voxel, vec3 rayOrigin, vec3 direction,
                       float maxDistance) {
    if (maxDistance <= 0.0) return false;
#if CHROMA_STATIC_WORLD
    float distance;
    return chromaVoxDataRayHit(data, voxel, rayOrigin, direction, maxDistance, distance);
#else
    if (((data.x | data.y | data.z | data.w) & 0x80000000u) != 0u) {
        vec3 lower = chromaVoxLower(voxel);
        float distance;
        return chromaVoxBoxRayHit(lower, lower + CHROMA_VOX_CELL, rayOrigin, direction, maxDistance, distance);
    }
    for (int slot = 0; slot < CHROMA_VOX_SURFACES; ++slot) {
        uint surface = data[slot];
        if (!chromaSurfelValid(surface) || chromaSurfelMask(surface) == 0u) continue;
        vec3 normal = chromaSurfelNormal(surface);
        int axis = chromaSurfelAxis(normal);
        float offset = (float((surface >> 8u) & 63u) / 63.0 - 0.5)
                     * CHROMA_VOX_CELL * dot(abs(normal), vec3(1.0));
        float height = dot(normal, chromaVoxCentre(voxel) - rayOrigin) + offset;
        float denominator = dot(normal, direction);
        if (abs(denominator) < 0.0000001) {
            if (abs(height) < 0.00001 && chromaSurfelCoveredAxis(surface, voxel, rayOrigin, axis)) return true;
            continue;
        }
        float hit = height / denominator;
        if (hit >= 0.0 && hit < maxDistance
            && chromaSurfelCoveredAxis(surface, voxel, rayOrigin + direction * hit, axis)) return true;
    }
    return false;
#endif
}
// Conservative packed occupancy is shared by nearest map tracing and the final
// visibility filter. Callers reject cells outside the current cache window.
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
#endif
