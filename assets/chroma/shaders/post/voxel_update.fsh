#version 450
#extension GL_ARB_separate_shader_objects : require
#include <minecraft:globals.glsl>
#include <chroma:lighting.glsl>
#include <chroma:auto_read.glsl>
#include <chroma:voxel_space.glsl>
uniform sampler2D PrevSampler;
uniform sampler2D MetaSampler;
uniform sampler2D InDepthSampler;
uniform sampler2D MatDecSampler;
uniform sampler2D CatalogSampler;
layout(location = 0) out vec4 fragColor;

// ponytail: eight interleaved world-Y slices bound update cost. Hidden edits
// remain unknown until observed; newly entering cells bypass the slice delay.
#ifndef CHROMA_VOX_UPDATE_PHASES
#define CHROMA_VOX_UPDATE_PHASES 8
#endif

bool evidencePixel(ivec2 p, ivec2 size) {
    if (any(lessThan(p, ivec2(2))) || any(greaterThanEqual(p, size - 2))) return false;
    if (chromaAutoHeaderPixel(p, size)) return false;
    return !chromaCatalogHas(CatalogSampler, chromaRawAddressAtPixel(p, size));
}
bool projectPixel(vec3 eye, mat4 projection, ivec2 size, out ivec2 p) {
    vec4 clip = projection * vec4(eye, 1.0);
    if (clip.w <= 0.0) return false;
    vec3 ndc = clip.xyz / clip.w;
    if (ndc.z <= 0.0 || ndc.z >= 1.0) return false;
    p = ivec2(floor((ndc.xy * 0.5 + 0.5) * vec2(size)));
    return evidencePixel(p, size);
}
vec3 eyeAt(ivec2 p, float depth, mat4 inverseProjection, ivec2 size) {
    vec2 uv = (vec2(p) + 0.5) / vec2(size);
    vec4 eye = inverseProjection * vec4(uv * 2.0 - 1.0, depth, 1.0);
    return eye.xyz / eye.w;
}
bool footprintVacant(ivec3 voxel, mat4 projection, mat4 inverseProjection,
                     mat3 rotation, ivec2 size) {
    vec3 low = chromaVoxCentre(voxel) - vec3(CHROMA_VOX_CELL * 0.5);
    vec3 high = low + vec3(CHROMA_VOX_CELL);
    ivec2 first = size, last = ivec2(-1);
    for (int i = 0; i < 8; ++i) {
        vec3 corner = mix(low, high, bvec3((i & 1) != 0, (i & 2) != 0, (i & 4) != 0));
        vec4 clip = projection * vec4(rotation * corner, 1.0);
        // Near clipping or an incomplete screen footprint provides no proof.
        if (clip.w <= 0.0) return false;
        vec3 ndc = clip.xyz / clip.w;
        if (ndc.z <= 0.0 || ndc.z >= 1.0) return false;
        ivec2 pixel = ivec2(floor((ndc.xy * 0.5 + 0.5) * vec2(size)));
        first = min(first, pixel); last = max(last, pixel);
    }
    if (any(lessThan(first, ivec2(2))) || any(greaterThanEqual(last, size - 2))) return false;
    mat3 inverseRotation = transpose(rotation);
    bool tested = false;
    // Only a proposed confidence decrease pays for this scan. A visible or
    // occluding surface exits immediately; empty footprints require all rays.
    // ponytail: large near-camera removals cost pixels; add a depth hierarchy only if profiling requires it.
    for (int y = first.y; y <= last.y; ++y) {
        for (int x = first.x; x <= last.x; ++x) {
            ivec2 pixel = ivec2(x, y);
            // Camera bob includes translation inside ProjMat. Two unprojected
            // points recover its actual ray; an origin-zero ray is incorrect.
            vec3 nearEye = eyeAt(pixel, 1.0, inverseProjection, size);
            vec3 farEye = eyeAt(pixel, 0.001, inverseProjection, size);
            vec3 start = inverseRotation * nearEye;
            vec3 direction = inverseRotation * (farEye - nearEye);
            vec3 inv = 1.0 / mix(direction, vec3(1e-20), lessThan(abs(direction), vec3(1e-7)));
            vec3 a = (low - start) * inv, b = (high - start) * inv;
            vec3 enter = min(a, b), leave = max(a, b);
            float nearT = max(max(enter.x, max(enter.y, enter.z)), 0.0);
            float farT = min(leave.x, min(leave.y, leave.z));
            if (farT <= nearT) continue;
            tested = true;
            if (!evidencePixel(pixel, size)) return false;
            float depth = texelFetch(InDepthSampler, pixel, 0).r;
            if (depth >= 0.999999) return false;
            if (depth <= 0.000001) continue;
            vec3 hit = inverseRotation * eyeAt(pixel, depth, inverseProjection, size);
            float rayLength2 = dot(direction, direction);
            float surfaceT = dot(hit - start, direction) / rayLength2;
            // Contact with the far face belongs to the neighbouring cell.
            // One millimetre absorbs unprojection roundoff without widening it
            // to a whole quarter-cell and erasing thin visible geometry.
            if (surfaceT < farT - 0.001 * inversesqrt(rayLength2)) return false;
        }
    }
    return tested;
}
uint clearObservedAir(ivec3 voxel, uint previous, mat4 projection,
                      mat4 inverseProjection, mat3 rotation, ivec2 size) {
    // Occupied cells get this cheap candidate check every frame. The final
    // footprint gate distinguishes an empty cell from a missed silhouette.
    vec3 centreEye = rotation * chromaVoxCentre(voxel);
    ivec2 p;
    if (!projectPixel(centreEye, projection, size, p)) return previous;
    float d = texelFetch(InDepthSampler, p, 0).r;
    if (d >= 0.999999) return previous;
    if (d <= 0.000001) return 0u;
    vec3 surface = eyeAt(p, d, inverseProjection, size);
    return centreEye.z > surface.z + CHROMA_VOX_CELL ? 0u : previous;
}
uint observe(ivec3 voxel, uint previous, mat4 projection, mat4 inverseProjection,
             mat3 rotation, ivec2 size) {
    vec3 centre = chromaVoxCentre(voxel);
    vec3 centreEye = rotation * centre;
    ivec2 p;
    if (!projectPixel(centreEye, projection, size, p)) return previous;
    float d = texelFetch(InDepthSampler, p, 0).r;
    // integrate_depth marks the precise hand/3D-HUD footprint with near depth.
    if (d >= 0.999999) return previous;
    if (d <= 0.000001) return 0u;
    vec3 surface = eyeAt(p, d, inverseProjection, size);
    // The centre suggests vacancy; main still requires full-footprint proof.
    if (centreEye.z > surface.z + 0.25) return 0u;
    if (abs(centreEye.z - surface.z) > 1.0) return previous;
    ivec2 px[4] = ivec2[4](p + ivec2(-1,0), p + ivec2(1,0),
                            p + ivec2(0,-1), p + ivec2(0,1));
    vec3 side[4];
    float distanceZ[4];
    for (int i = 0; i < 4; ++i) {
        side[i] = surface;
        distanceZ[i] = 1.0e20;
        if (evidencePixel(px[i], size)) {
            float sd = texelFetch(InDepthSampler, px[i], 0).r;
            if (sd > 0.000001 && sd < 0.999999) {
                side[i] = eyeAt(px[i], sd, inverseProjection, size);
                distanceZ[i] = abs(side[i].z - surface.z);
            }
        }
    }
    int horizontal = distanceZ[1] < distanceZ[0] ? 1 : 0;
    int vertical = distanceZ[3] < distanceZ[2] ? 3 : 2;
    if (distanceZ[horizontal] > 1.0 || distanceZ[vertical] > 1.0) return previous;
    vec3 dx = horizontal == 1 ? side[1]-surface : surface-side[0];
    vec3 dy = vertical == 3 ? side[3]-surface : surface-side[2];
    vec3 crossNormal = cross(dx, dy);
    if (dot(crossNormal, crossNormal) < 1e-16) return previous;
    vec3 normalEye = normalize(crossNormal);
    if (dot(normalEye, surface) > 0.0) normalEye = -normalEye;
    // Only the selected local triangle defines this surface. Its unused
    // neighbors may be background at a fence, slab, stair, or entity silhouette.
    vec3 normal = normalize(transpose(rotation) * normalEye);
    int axis = abs(normal.x) > abs(normal.y) ? 0 : 1;
    if (abs(normal.z) > abs(normal[axis])) axis = 2;
    if (abs(normal[axis]) > 0.98) {
        float s = sign(normal[axis]);
        normal = vec3(0.0); normal[axis] = s;
    }
    // Project onto the observed surface plane. A slab, fence rail or moving
    // entity face can lie inside this cell, not at its outward quarter-grid face.
    // Reject planes outside the cell's normal extent before probing them.
    float planeOffset = dot(transpose(rotation) * surface - centre, normal);
    float cellExtent = CHROMA_VOX_CELL * 0.5 * dot(abs(normal), vec3(1.0));
    bool clearPlane = false;
    if (previous > 0u && planeOffset <= -cellExtent + 0.001) {
        // A removed caster can leave a cell touching the floor: the conservative
        // eye-depth margin misses it, and a probe on the floor has zero gap.
        // Clear only against a locally confirmed plane, not a silhouette pair.
        clearPlane = true;
        for (int i = 0; i < 4; ++i)
            if (distanceZ[i] > 1.0 || abs(dot(side[i] - surface, normalEye)) > 0.01)
                clearPlane = false;
    }
    // The centre pixel may see background while the projected probe sees a
    // small solid in this cell. Let that positive hit win before clearing;
    // otherwise a fixed scene alternates empty/occupied every update slice.
    uint unresolved = clearPlane ? 0u : previous;
    float planeLimit = cellExtent + 0.02;
    if (abs(planeOffset) > planeLimit) return unresolved;
    vec3 probe = centre + normal * planeOffset;
    vec3 probeEye = rotation * probe;
    ivec2 q;
    if (!projectPixel(probeEye, projection, size, q)) return unresolved;
    float qd = texelFetch(InDepthSampler, q, 0).r;
    if (qd >= 0.999999) return unresolved;
    if (qd <= 0.000001) return clearPlane ? 0u : (previous > 0u ? previous - 1u : 0u);
    vec3 hitEye = eyeAt(q, qd, inverseProjection, size);
    vec3 hit = transpose(rotation) * hitEye;
    if (length(hit - probe) <= 0.15 && abs(dot(hit - centre, normal)) <= planeLimit) {
        ivec3 hitCell = chromaVoxOf(hit - normal * 0.02);
        // A depth sample belongs to one exact quarter-cell. Checking all axes
        // avoids expanding a thin silhouette sideways into adjacent empty cells.
        if (all(equal(hitCell, voxel))) return 3u;
    }
    if (clearPlane) return 0u;
    if (probeEye.z > hitEye.z + 0.10) return previous > 0u ? previous - 1u : 0u;
    return previous;
}
void main() {
    ivec2 p = ivec2(gl_FragCoord.xy);
    if (!chromaMdValid(MatDecSampler, 0)) {
        fragColor = texelFetch(PrevSampler, p, 0); return;
    }
    uint oldWord = chromaVoxDecode(texelFetch(PrevSampler, p, 0));
    bool valid = chromaVoxDecode(texelFetch(MetaSampler, ivec2(0,0), 0)) == CHROMA_VOX_META_MAGIC;
    ivec3 previousOrigin;
    for (int i = 0; i < 3; ++i)
        previousOrigin[i] = int(chromaVoxDecode(texelFetch(MetaSampler, ivec2(i+1,0), 0)));
    uint frame = chromaVoxDecode(texelFetch(MetaSampler, ivec2(4,0), 0));
    ivec3 origin = chromaVoxOrigin();
    ivec3 wrapped = ivec3((p.x % 16) * 16, p.y, p.x / 16);
    ivec3 first = origin + ((wrapped - origin) & (CHROMA_VOX_N - 1));
    bool updateSlice = (first.y % CHROMA_VOX_UPDATE_PHASES + CHROMA_VOX_UPDATE_PHASES)
        % CHROMA_VOX_UPDATE_PHASES == int(frame % uint(CHROMA_VOX_UPDATE_PHASES));
    if (valid && !updateSlice && all(equal(origin, previousOrigin))
            && (oldWord & 0xAAAAAAAAu) == 0u) {
        fragColor = chromaVoxEncode(oldWord); return;
    }
    mat4 projection;
    for (int i = 0; i < 16; ++i) projection[i/4][i%4] = chromaMdFloat(MatDecSampler, 1+i);
    mat4 inverseProjection = chromaMdInvProj(MatDecSampler, 0);
    mat3 rotation = chromaMdRot(MatDecSampler, 0);
    ivec2 size = textureSize(InDepthSampler, 0);
    uint result = 0u;
    for (int i = 0; i < 16; ++i) {
        // A packed word can straddle the moving window's X boundary.
        ivec3 voxel = origin + ((wrapped + ivec3(i,0,0) - origin) & (CHROMA_VOX_N - 1));
        bool retained = valid && chromaVoxContains(voxel, previousOrigin);
        uint confidence = retained ? (oldWord >> uint(i * 2)) & 3u : 0u;
        uint previousConfidence = confidence;
        if (updateSlice || !retained) confidence = observe(voxel, confidence, projection, inverseProjection, rotation, size);
        else if (confidence >= 2u) confidence = clearObservedAir(voxel, confidence,
                projection, inverseProjection, rotation, size);
        // Acquisition can hit any visible part of a voxel. Every downward path
        // (sky, centre depth, probe or contact plane) needs equally broad proof.
        if (retained && previousConfidence > 0u && confidence < previousConfidence
                && !footprintVacant(voxel, projection, inverseProjection, rotation, size))
            confidence = previousConfidence;
        result |= confidence << uint(i * 2);
    }
    fragColor = chromaVoxEncode(result);
}
