#version 450
#extension GL_ARB_separate_shader_objects : require
#include <minecraft:globals.glsl>
#include <chroma:lighting.glsl>
#include <chroma:auto_read.glsl>
#include <chroma:voxel_space.glsl>
uniform sampler2D PrevSampler;
uniform sampler2D MetaSampler;
uniform sampler2D InDepthSampler;
uniform sampler2D SurfaceNormalSampler;
uniform sampler2D VacancyDepthSampler;
#if !CHROMA_STATIC_WORLD && (CHROMA_PARTICLE_DEPTH_MASK || (CHROMA_ENTITY_SHADOWS != 1 && CHROMA_TRANSPARENT_DEPTH_MASK))
uniform sampler2D MainColorSampler;
#endif
uniform sampler2D CatalogSampler;
layout(location = 0) flat in int cameraValid;
layout(location = 1) flat in mat4 cameraProj;
layout(location = 5) flat in mat4 cameraInvProj;
layout(location = 9) flat in mat3 cameraRot;
layout(location = 12) flat in int historyValid;
layout(location = 13) flat in ivec3 previousOrigin;
layout(location = 14) flat in uint frame;
layout(location = 0) out vec4 fragColor;
#include <chroma:depth_support.glsl>

// ponytail: eight interleaved world-coordinate phases bound update cost. Hidden edits
// remain unknown until observed; newly entering cells bypass the slice delay.


bool projectPixel(vec3 eye, mat4 projection, ivec2 size, out ivec2 p) {
    vec4 clip = projection * vec4(eye, 1.0);
    if (clip.w <= 0.0) return false;
    vec3 ndc = clip.xyz / clip.w;
    if (ndc.z <= 0.0 || ndc.z >= 1.0) return false;
    p = ivec2(floor((ndc.xy * 0.5 + 0.5) * vec2(size)));
    return evidencePixel(p, size);
}

// All pixels must lie beyond the farthest corner plus the legacy clearance.
// Inverse-W bounds include arbitrary NDC x/y and finite reverse-Z projections.
float vacancyDepthLimit(float farthestW, mat4 inverseProjection) {
    vec4 w = vec4(inverseProjection[0][3], inverseProjection[1][3],
                  inverseProjection[2][3], inverseProjection[3][3]);
    float xy = abs(w.x) + abs(w.y);
    if (any(isnan(w)) || any(isinf(w)) || !(w.z > 0.0)
            || !(farthestW > 0.0) || isinf(farthestW)
            || !(w.w - xy + w.z * 0.000001 > 0.0)) return -1.0;
    // .001 exceeds the exact plane test's .0001-W tolerance. Round downward.
    return (1.0 / (farthestW + 0.001) - w.w - xy) / w.z - 0.0000001;
}
bool vacancyTileClear(ivec2 tile, float depthLimit) {
    float depth = uintBitsToFloat(chromaVoxDecode(texelFetch(VacancyDepthSampler, tile, 0)));
    return depthLimit > 0.0 && depthLimit < 0.999999 && depth < depthLimit;
}

bool footprintVacantBox(vec3 low, vec3 high, mat4 projection, mat4 inverseProjection,
                        mat3 rotation, ivec2 size) {
    ivec2 first = size, last = ivec2(-1);
    float farthestW = 0.0;
    for (int i = 0; i < 8; ++i) {
        vec3 corner = mix(low, high, bvec3((i & 1) != 0, (i & 2) != 0, (i & 4) != 0));
        vec4 clip = projection * vec4(rotation * corner, 1.0);
        // Near clipping or an incomplete screen footprint provides no proof.
        if (clip.w <= 0.0) return false;
        vec3 ndc = clip.xyz / clip.w;
        if (ndc.z <= 0.0 || ndc.z >= 1.0) return false;
        farthestW = max(farthestW, clip.w);
        ivec2 pixel = ivec2(floor((ndc.xy * 0.5 + 0.5) * vec2(size)));
        first = min(first, pixel); last = max(last, pixel);
    }
    if (any(lessThan(first, ivec2(2))) || any(greaterThanEqual(last, size - 2))) return false;
    mat3 inverseRotation = transpose(rotation);
    bool tested = false;
    float depthLimit = vacancyDepthLimit(farthestW, inverseProjection);
    ivec2 tileSize = (size + textureSize(VacancyDepthSampler, 0) - 1) / textureSize(VacancyDepthSampler, 0);
    // Only a proposed confidence decrease pays for this scan. A visible or
    // occluding surface exits immediately; empty footprints require all rays.
    // ponytail: uncertain tiles retain exact rays; add more hierarchy only if profiling requires it.
    for (int ty = first.y / tileSize.y; ty <= last.y / tileSize.y; ++ty) {
        for (int tx = first.x / tileSize.x; tx <= last.x / tileSize.x; ++tx) {
            // A tile bound never establishes that a subpixel footprint was seen.
            // Preserve the original tested flag; uncertain tiles use exact rays.
            if (tested && vacancyTileClear(ivec2(tx, ty), depthLimit)) continue;
            ivec2 lowPixel = max(first, ivec2(tx, ty) * tileSize);
            ivec2 highPixel = min(last, (ivec2(tx, ty) + 1) * tileSize - 1);
            for (int y = lowPixel.y; y <= highPixel.y; ++y) {
                for (int x = lowPixel.x; x <= highPixel.x; ++x) {
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
        }
    }
    return tested;
}
bool footprintVacant(ivec3 voxel, mat4 projection, mat4 inverseProjection,
                     mat3 rotation, ivec2 size) {
    vec3 low = chromaVoxLower(voxel);
    return footprintVacantBox(low, low + CHROMA_VOX_CELL, projection,
                             inverseProjection, rotation, size);
}

void observeBox(vec3 centre, float cellSize, ivec3 expectedCell,
                mat4 projection, mat4 inverseProjection, mat3 rotation, ivec2 size,
                out bool positive, out vec3 hitPosition, out vec3 hitNormal) {
    positive = false;
    hitPosition = centre;
    hitNormal = vec3(0.0);
    float push = cellSize * 0.08;
    vec3 centreEye = rotation * centre;
    ivec2 p;
    if (!projectPixel(centreEye, projection, size, p)) return;
    float d = texelFetch(InDepthSampler, p, 0).r;
    // integrate_depth marks the precise hand/3D-HUD footprint with near depth.
    if (d >= 0.999999 || d <= 0.000001) return;
    vec3 surface = eyeAt(p, d, inverseProjection, size);
    if (centreEye.z > surface.z + cellSize) return;
    if (abs(centreEye.z - surface.z) > 1.0) return;
    uint cachedNormal = chromaVoxDecode(texelFetch(SurfaceNormalSampler, p, 0));
    if ((cachedNormal & 0x40000000u) == 0u) return;
    vec3 normal = chromaDepthNormalDecode(cachedNormal);
    vec3 observedNormal = (cachedNormal & 0x80000000u) != 0u ? normal : vec3(0.0);
    int axis = chromaSurfelAxis(normal);
    if (abs(normal[axis]) > 0.98) {
        float s = sign(normal[axis]);
        normal = vec3(0.0); normal[axis] = s;
    }
    // Project onto the observed surface plane. A slab, fence rail or moving
    // entity face can lie inside this cell, not at its outward quarter-grid face.
    // Reject planes outside the cell's normal extent before probing them.
    float planeOffset = dot(transpose(rotation) * surface - centre, normal);
    float cellExtent = cellSize * 0.5 * dot(abs(normal), vec3(1.0));
    // Only positive native hits leave this helper. Plane/patch footprint proofs
    // below decide removal; the former cell-confidence result was unused.
    float planeLimit = cellExtent + push;
    if (abs(planeOffset) > planeLimit) return;
    vec3 probe = centre + normal * planeOffset;
    vec3 probeEye = rotation * probe;
    ivec2 q;
    if (!projectPixel(probeEye, projection, size, q)) return;
    float qd = texelFetch(InDepthSampler, q, 0).r;
    if (qd >= 0.999999 || qd <= 0.000001) return;
    vec3 hitEye = eyeAt(q, qd, inverseProjection, size);
    vec3 hit = transpose(rotation) * hitEye;
    if (length(hit - probe) <= 0.15 && abs(dot(hit - centre, normal)) <= planeLimit) {
        int grid = int(round(1.0 / cellSize));
        ivec3 hitCell = CameraBlockPos * grid
            + ivec3(floor((hit - normal * push - CameraOffset) * float(grid)));
        // A depth sample belongs to one exact quarter-cell. Checking all axes
        // avoids expanding a thin silhouette sideways into adjacent empty cells.
        if (all(equal(hitCell, expectedCell))) {
            positive = true;
            hitPosition = hit;
            hitNormal = abs(dot(hit - transpose(rotation) * surface, observedNormal)) < 0.002
                ? observedNormal : vec3(0.0);
            return;
        }
    }
}
// A mask is attached to an actual surface plane. Empty space behind a cutout
// is evidence for that plane patchCoord, not a claim that an entire 3D cube is empty.
uint surfaceBit(vec3 hit, vec3 normal, ivec3 voxel) {
    int axis = chromaSurfelAxis(normal);
    ivec3 patchCoord = clamp(ivec3(floor((hit - chromaVoxLower(voxel)) * 16.0)), ivec3(0), ivec3(3));
    return 1u << uint(patchCoord[(axis + 1) % 3] + 4 * patchCoord[(axis + 2) % 3]);
}
bool planeFootprintVacant(ivec3 voxel, vec3 point, vec3 normal, ivec2 size);
void acquireSurface(vec3 hit, vec3 normal, ivec3 voxel, inout uvec4 records,
                    inout vec3 points[4], inout vec3 normals[4], inout uvec4 positives,
                    inout bvec4 retainedPlanes, ivec2 size) {
    // A later matching probe must not overwrite this update's overflow flag.
    if (((records.x | records.y | records.z | records.w) & 0x80000000u) != 0u) return;
    if (dot(normal, normal) < 0.5) return;
    uint candidate = chromaSurfelEncode(hit, normal, voxel, 65535u);
    vec3 encodedNormal = chromaSurfelNormal(candidate);
    vec3 encodedPoint = chromaSurfelPoint(candidate, voxel);
    int chosen = -1;
    for (int i = 0; i < CHROMA_VOX_SURFACES; ++i) {
        if (!chromaSurfelValid(records[i])) continue;
        // Eight-bit normal quantization can exceed the raw-normal angle gate.
        // The same encoded plane (including its reverse side) remains one slot.
        vec3 storedNormal = chromaSurfelNormal(records[i]);
        float offset = (float((records[i] >> 8u) & 63u) / 63.0 - 0.5)
                     * CHROMA_VOX_CELL * dot(abs(storedNormal), vec3(1.0));
        vec3 storedPoint = chromaVoxCentre(voxel) + storedNormal * offset;
        bool sameEncoded = abs(dot(encodedNormal, storedNormal)) > 0.99999;
        if ((sameEncoded || abs(dot(normal, normals[i])) > 0.98)
                && abs(dot(encodedPoint - storedPoint, storedNormal)) < 0.012) { chosen = i; break; }
    }
    if (chosen < 0) {
        for (int i = 0; i < CHROMA_VOX_SURFACES; ++i)
            if (!chromaSurfelValid(records[i])) { chosen = i; break; }
    }
    if (chosen < 0) {
        // A moving object may leave visible-empty old planes before its
        // next face arrives. Recycle proved air before latching full-cell fill;
        // unknown planes and this update's positive hits remain protected.
        for (int i = 0; i < CHROMA_VOX_SURFACES; ++i) {
            if (retainedPlanes[i] && positives[i] == 0u
                    && planeFootprintVacant(voxel, points[i], normals[i], size)) {
                chosen = i;
                records[i] = 0u;
                retainedPlanes[i] = false;
                break;
            }
        }
    }
    // More than four distinct surfaces cannot be represented in this cell.
    // Preserve conservative occlusion until the complete cell is observed empty.
    if (chosen < 0) { records.w |= 0x80000000u; return; }
    uint mask = chromaSurfelValid(records[chosen]) ? chromaSurfelMask(records[chosen]) : 65535u;
    uint encoded = chromaSurfelEncode(hit, normal, voxel, mask);
    vec3 quantizedNormal = chromaSurfelNormal(encoded);
    if (chromaSurfelValid(records[chosen])
            && chromaSurfelAxis(chromaSurfelNormal(records[chosen])) != chromaSurfelAxis(quantizedNormal)) {
        mask = 65535u;
        positives[chosen] = 0u;
        encoded = chromaSurfelEncode(hit, normal, voxel, mask);
    }
    records[chosen] = encoded;
    // This frame's alpha observations use the exact measured plane. The stored
    // normal/offset are quantized only for persistent use and ray intersections.
    points[chosen] = hit;
    normals[chosen] = normal;
    positives[chosen] |= surfaceBit(hit, quantizedNormal, voxel);
}
int planeEvidence(vec3 point, vec3 planePoint, vec3 normal, ivec3 voxel,
                  int axis, int bit, ivec2 size) {
    vec3 eye = cameraRot * point;
    ivec2 p;
    if (!projectPixel(eye, cameraProj, size, p)) return -1;
    float depth = texelFetch(InDepthSampler, p, 0).r;
    if (depth >= 0.999999) return -1;
    if (depth <= 0.000001) return 0;
    vec3 surfaceEye = eyeAt(p, depth, cameraInvProj, size);
    vec3 surface = transpose(cameraRot) * surfaceEye;
    float tolerance = max(abs(normal.x), max(abs(normal.y), abs(normal.z))) > 0.99999 ? 0.005 : 0.035;
    if (abs(dot(surface - planePoint, normal)) <= tolerance) {
        // Proximity alone accepts a perpendicular face at a thin corner. Share
        // the independently supported native normal used for plane acquisition.
        uint cachedNormal = chromaVoxDecode(texelFetch(SurfaceNormalSampler, p, 0));
        if ((cachedNormal & 0xc0000000u) != 0xc0000000u) return -1;
        vec3 supportedNormal = chromaDepthNormalDecode(cachedNormal);
        ivec3 patchCoord = ivec3(floor((surface - chromaVoxLower(voxel)) * 16.0));
        bool inPatch = patchCoord[(axis + 1) % 3] == (bit & 3)
            && patchCoord[(axis + 2) % 3] == (bit >> 2);
        // A raster pixel landing on an adjacent patch cannot stamp this bit.
        // .95 also accepts the worst angular error of the stored 8-bit normal.
        if (abs(dot(supportedNormal, normal)) >= 0.95) return inPatch ? 1 : -1;
    }
    float surfaceW = (cameraProj * vec4(surfaceEye, 1.0)).w;
    float planeW = (cameraProj * vec4(eye, 1.0)).w;
    return surfaceW > planeW + 0.0001 ? 0 : -1;
}
bool planeFootprintVacantBox(vec3 low, vec3 high, vec3 planePoint, vec3 normal, ivec2 size) {
    ivec2 first = size, last = ivec2(-1);
    float farthestW = 0.0;
    int axis = chromaSurfelAxis(normal), u = (axis + 1) % 3, v = (axis + 2) % 3;
    // Project the actual plane rectangle, not the surrounding 3D volume.
    // Its clipped portion remains inside these four projected corners.
    for (int i = 0; i < 4; ++i) {
        vec3 corner = low;
        corner[u] = (i & 1) != 0 ? high[u] : low[u];
        corner[v] = (i & 2) != 0 ? high[v] : low[v];
        corner[axis] = planePoint[axis] - (normal[u] * (corner[u] - planePoint[u])
            + normal[v] * (corner[v] - planePoint[v])) / normal[axis];
        vec4 clip = cameraProj * vec4(cameraRot * corner, 1.0);
        if (clip.w <= 0.0) return false;
        vec3 ndc = clip.xyz / clip.w;
        if (ndc.z <= 0.0 || ndc.z >= 1.0) return false;
        farthestW = max(farthestW, clip.w);
        ivec2 pixel = ivec2(floor((ndc.xy * 0.5 + 0.5) * vec2(size)));
        first = min(first, pixel); last = max(last, pixel);
    }
    if (any(lessThan(first, ivec2(2))) || any(greaterThanEqual(last, size - 2))) return false;
    mat3 inverseRotation = transpose(cameraRot);
    bool tested = false;
    float depthLimit = vacancyDepthLimit(farthestW, cameraInvProj);
    ivec2 tileSize = (size + textureSize(VacancyDepthSampler, 0) - 1) / textureSize(VacancyDepthSampler, 0);
    for (int ty = first.y / tileSize.y; ty <= last.y / tileSize.y; ++ty) {
        for (int tx = first.x / tileSize.x; tx <= last.x / tileSize.x; ++tx) {
            // A tile bound never establishes that a subpixel footprint was seen.
            // Preserve the original tested flag; uncertain tiles use exact rays.
            if (tested && vacancyTileClear(ivec2(tx, ty), depthLimit)) continue;
            ivec2 lowPixel = max(first, ivec2(tx, ty) * tileSize);
            ivec2 highPixel = min(last, (ivec2(tx, ty) + 1) * tileSize - 1);
            for (int y = lowPixel.y; y <= highPixel.y; ++y) {
                for (int x = lowPixel.x; x <= highPixel.x; ++x) {
                    ivec2 p = ivec2(x, y);
                    vec3 nearEye = eyeAt(p, 1.0, cameraInvProj, size);
                    vec3 farEye = eyeAt(p, 0.001, cameraInvProj, size);
                    vec3 start = inverseRotation * nearEye;
                    vec3 direction = inverseRotation * (farEye - nearEye);
                    float denominator = dot(direction, normal);
                    if (abs(denominator) < 1e-8) continue;
                    float t = dot(planePoint - start, normal) / denominator;
                    if (t <= 0.0) continue;
                    vec3 hit = start + direction * t;
                    if (any(lessThan(hit, low - 0.00001)) || any(greaterThan(hit, high + 0.00001))) continue;
                    tested = true;
                    if (!evidencePixel(p, size)) return false;
                    float depth = texelFetch(InDepthSampler, p, 0).r;
                    if (depth >= 0.999999) return false;
                    if (depth <= 0.000001) continue;
                    vec3 surfaceEye = eyeAt(p, depth, cameraInvProj, size);
                    float nativeW = (cameraProj * vec4(surfaceEye, 1.0)).w;
                    float planeW = (cameraProj * vec4(cameraRot * hit, 1.0)).w;
                    if (nativeW <= planeW + 0.0001) return false;
                }
            }
        }
    }
    return tested;
}
bool planeFootprintVacant(ivec3 voxel, vec3 point, vec3 normal, ivec2 size) {
    vec3 low = chromaVoxLower(voxel);
    return planeFootprintVacantBox(low, low + CHROMA_VOX_CELL, point, normal, size);
}
bool planePatchVacant(ivec3 voxel, vec3 point, vec3 normal, int axis, int bit, ivec2 size) {
    int u = (axis + 1) % 3, v = (axis + 2) % 3;
    vec3 low = chromaVoxLower(voxel), high = low + CHROMA_VOX_CELL;
    low[u] += float(bit & 3) / 16.0; high[u] = low[u] + 1.0 / 16.0;
    low[v] += float(bit >> 2) / 16.0; high[v] = low[v] + 1.0 / 16.0;
    return planeFootprintVacantBox(low, high, point, normal, size);
}
uint refineSurface(uint record, ivec3 voxel, vec3 point, vec3 normal,
                   uint positives, bool retained, ivec2 size) {
    if (!chromaSurfelValid(record)) return record;
    uint oldMask = chromaSurfelMask(record), mask = oldMask;
    int axis = chromaSurfelAxis(chromaSurfelNormal(record));
    int u = (axis + 1) % 3, v = (axis + 2) % 3;
    vec3 low = chromaVoxLower(voxel);
    for (int bit = 0; bit < 16; ++bit) {
        // A positive native hit always wins this bit, so other probes cannot
        // change its final result. Common opaque faces need one probe per bit.
        if ((positives & (1u << uint(bit))) != 0u) { mask |= 1u << uint(bit); continue; }
        bool clear = true, anyClear = false, occupied = false;
        for (int probe = 0; probe < 4; ++probe) {
            vec3 samplePoint = low;
            samplePoint[u] += (float(bit & 3) + (float(probe & 1) + 0.5) * 0.5) / 16.0;
            samplePoint[v] += (float(bit >> 2) + (float(probe >> 1) + 0.5) * 0.5) / 16.0;
            samplePoint[axis] = point[axis]
                - (normal[u] * (samplePoint[u] - point[u]) + normal[v] * (samplePoint[v] - point[v])) / normal[axis];
            int evidence = -1;
            if (samplePoint[axis] >= low[axis] - 0.0001 && samplePoint[axis] <= low[axis] + CHROMA_VOX_CELL + 0.0001)
                evidence = planeEvidence(samplePoint, point, normal, voxel, axis, bit, size);
            clear = clear && evidence == 0;
            anyClear = anyClear || evidence == 0;
            occupied = occupied || evidence == 1;
            if (occupied) break;
        }
        if (occupied) mask |= 1u << uint(bit);
        else if (anyClear && (positives & (1u << uint(bit))) == 0u) {
            // Retained geometry, or a mixed clear/unknown edge stencil, needs
            // the complete patch footprint. Fully unknown patches stay intact.
            bool erase = clear && (!retained || (oldMask & (1u << uint(bit))) == 0u);
            if (!erase) erase = planePatchVacant(voxel, point, normal, axis, bit, size);
            if (erase) mask &= ~(1u << uint(bit));
        }
    }
    mask |= positives;
    // Do not erase a retained plane just because sixteen patchCoord probes miss a
    // thin silhouette. Complete removal requires all its projected raster rays.
    if (mask == 0u && retained && oldMask != 0u
            && !planeFootprintVacant(voxel, point, normal, size)) mask = oldMask;
    return mask == 0u ? 0u : (record & ~(65535u << 14u)) | (mask << 14u);
}
void main() {
    ivec2 p = ivec2(gl_FragCoord.xy);
    if (cameraValid == 0) discard;
    int index = p.x + 4096 * p.y;
    int slot = index & 3;
    index >>= 2;
    ivec3 wrapped = ivec3(index % CHROMA_VOX_N,
        (index / CHROMA_VOX_N) % CHROMA_VOX_N, index / (CHROMA_VOX_N * CHROMA_VOX_N));
    ivec3 origin = chromaVoxOrigin();
    ivec3 voxel = origin + ((wrapped - origin) & (CHROMA_VOX_N - 1));
    bool retained = historyValid != 0 && chromaVoxContains(voxel, previousOrigin);
    bool updateSlice = chromaVoxUpdateSlice(voxel, frame);
    // Persistent output equals history before this pass. Leave unchanged cells
    // untouched; the history pass uses exactly the same phase and prior origin.
    if (retained && !updateSlice) discard;
    uvec4 records = uvec4(0u);
    if (retained) {
        for (int i = 0; i < CHROMA_VOX_SURFACES; ++i)
            records[i] = chromaVoxDecode(texelFetch(PrevSampler, chromaVoxSurfaceTexel(voxel, i), 0));
    }
    ivec2 size = textureSize(InDepthSampler, 0);
    if (((records.x | records.y | records.z | records.w) & 0x80000000u) != 0u) {
        if (footprintVacant(voxel, cameraProj, cameraInvProj, cameraRot, size)) records = uvec4(0u);
        fragColor = chromaVoxEncode(records[slot]); return;
    }
    vec3 points[4], normals[4];
    bvec4 hadPlane = bvec4(false);
    for (int i = 0; i < CHROMA_VOX_SURFACES; ++i) {
        hadPlane[i] = chromaSurfelValid(records[i]);
        points[i] = vec3(0.0); normals[i] = vec3(0.0);
        if (hadPlane[i]) {
            normals[i] = chromaSurfelNormal(records[i]);
            float offset = (float((records[i] >> 8u) & 63u) / 63.0 - 0.5)
                         * CHROMA_VOX_CELL * dot(abs(normals[i]), vec3(1.0));
            points[i] = chromaVoxCentre(voxel) + normals[i] * offset;
        }
    }
    uvec4 positives = uvec4(0u);
    bool positive;
    vec3 hit, normal;
    observeBox(chromaVoxCentre(voxel), CHROMA_VOX_CELL, voxel,
        cameraProj, cameraInvProj, cameraRot, size, positive, hit, normal);
    // A quantized oblique plane can have a subpixel clipped footprint forever.
    // The existing complete volume proof still confirms that this whole cell
    // is empty, including every raster ray through any missed thin silhouette.
    if (!positive && any(hadPlane)
            && footprintVacant(voxel, cameraProj, cameraInvProj, cameraRot, size)) {
        fragColor = vec4(0.0); return;
    }
    bool refine = positive || any(hadPlane);
    if (positive) acquireSurface(hit, normal, voxel, records, points, normals, positives, hadPlane, size);
    if (refine) {
        vec3 low = chromaVoxLower(voxel);
        float subSize = CHROMA_VOX_CELL * 0.5;
        for (int bit = 0; bit < 8; ++bit) {
            ivec3 sub = ivec3(bit & 1, (bit >> 1) & 1, (bit >> 2) & 1);
            observeBox(low + (vec3(sub) + 0.5) * subSize, subSize, voxel * 2 + sub,
                cameraProj, cameraInvProj, cameraRot, size, positive, hit, normal);
            if (positive) acquireSurface(hit, normal, voxel, records, points, normals, positives, hadPlane, size);
        }
        // Acquisition and overflow are cell-wide; mask refinement is independent
        // per record. This fragment emits only its own slot.
        if (((records.x | records.y | records.z | records.w) & 0x80000000u) == 0u)
            records[slot] = refineSurface(records[slot], voxel, points[slot], normals[slot], positives[slot], hadPlane[slot], size);
    }
    fragColor = chromaVoxEncode(records[slot]);
}
