#ifndef CHROMA_SHADOW_FILTER
#define CHROMA_SHADOW_FILTER
#include <chroma:voxel_space.glsl>
#if CHROMA_STATIC_WORLD
#include <chroma:shadow_filter_static.glsl>
#else
uniform sampler2D ShadowSampler;
uniform sampler2D SurfaceSampler;
uniform sampler2D VoxelSampler;
uniform sampler2D VoxelLod1Sampler;
const int CHROMA_SHADOW_RES = 128;
const ivec2 CHROMA_BLOCKER_OFFSETS[9] = ivec2[9](
    ivec2(0,0), ivec2(-1,0), ivec2(1,0), ivec2(0,-1), ivec2(0,1),
    ivec2(-1,-1), ivec2(1,-1), ivec2(-1,1), ivec2(1,1));

const vec2 CHROMA_SEARCH_DISK[9] = vec2[9](
    vec2(0.0000000000, 0.0000000000),
    vec2(-0.2606992670, 0.2388218838),
    vec2(0.0437128626, -0.4980855204),
    vec2(0.3725911869, 0.4859792253),
    vec2(-0.6962975829, -0.1231652390),
    vec2(0.6670471304, -0.4243207817),
    vec2(-0.2248239243, 0.8363337869),
    vec2(-0.4311390418, -0.8301319935),
    vec2(0.9393212956, 0.3430386329));
#if CHROMA_SHADOW_SAMPLES == 8
const vec2 CHROMA_SOURCE_DISK[8] = vec2[8](
    vec2(0.2500000000, 0.0000000000),
    vec2(-0.3192900903, 0.2924958773),
    vec2(0.0488724662, -0.5568765411),
    vec2(0.4024444781, 0.5249175574),
    vec2(-0.7385351138, -0.1306364636),
    vec2(0.6996049325, -0.4450313903),
    vec2(-0.2340041596, 0.8704838042),
    vec2(-0.4462713061, -0.8592682476));
#else
const vec2 CHROMA_SOURCE_DISK[16] = vec2[16](
    vec2(0.1767766953, 0.0000000000),
    vec2(-0.2257721880, 0.2068258183),
    vec2(0.0345580522, -0.3937711785),
    vec2(0.2845712195, 0.3711727644),
    vec2(-0.5222231871, -0.0923739293),
    vec2(0.4946953920, -0.3146847139),
    vec2(-0.1654659281, 0.6155250008),
    vec2(-0.3155614668, -0.6075944047),
    vec2(0.6846421610, 0.2500302208),
    vec2(-0.7122560869, 0.2940089567),
    vec2(0.3433545007, -0.7337286193),
    vec2(0.2537302385, 0.8089319910),
    vec2(-0.7647458905, -0.4431858785),
    vec2(0.8971339843, -0.1972323865),
    vec2(-0.5475069078, 0.7787722298),
    vec2(-0.1264867689, -0.9760896974));
#endif

vec3 chromaShadowReceiver(vec3 receiver, vec3 normal) {
#if CHROMA_SHADOW_PIXELATE
    float subdivisions = float(max(CHROMA_SHADOW_PIXELS_PER_BLOCK, 1));
    // CameraBlockPos is integral, so this small local coordinate has exactly
    // the world grid's phase, including negative and very large world positions.
    vec3 snapped = (floor((receiver - CameraOffset) * subdivisions) + 0.5)
                 / subdivisions + CameraOffset;
    vec3 a = abs(normal);
    // Reconstructed normals carry float noise: give near-ties a stable priority.
    int axis = a.x >= max(a.y, a.z) - 0.001 ? 0 : (a.y >= a.z - 0.001 ? 1 : 2);
    if (a[axis] < 0.0001) return receiver;
    vec3 delta = snapped - receiver;
    delta[axis] = 0.0;
    // Snap the two surface axes, then solve the third on the receiver plane.
    // Slabs and sloped entity faces must not be pushed inside their own voxels.
    delta[axis] = -dot(delta, normal) / normal[axis];
    return receiver + delta;
#else
    return receiver;
#endif
}

vec2 chromaShadowUV(vec3 direction) {
    direction /= abs(direction.x) + abs(direction.y) + abs(direction.z);
    vec2 uv = direction.xy;
    if (direction.z < 0.0)
        uv = (1.0 - abs(uv.yx)) * mix(vec2(-1), vec2(1), greaterThanEqual(uv, vec2(0)));
    return uv * 0.5 + 0.5;
}
ivec2 chromaShadowSeam(ivec2 p) {
    int n = CHROMA_SHADOW_RES;
    if (p.x < 0) { p.x = -p.x - 1; p.y = n - 1 - p.y; }
    if (p.x >= n) { p.x = 2*n - 1 - p.x; p.y = n - 1 - p.y; }
    if (p.y < 0) { p.y = -p.y - 1; p.x = n - 1 - p.x; }
    if (p.y >= n) { p.y = 2*n - 1 - p.y; p.x = n - 1 - p.x; }
    return p;
}
float chromaShadowDepth(int lamp, ivec2 p) {
    ivec2 tile = ivec2(lamp % 16, lamp / 16) * CHROMA_SHADOW_RES;
    return uintBitsToFloat(chromaVoxDecode(texelFetch(ShadowSampler, tile + chromaShadowSeam(p), 0)));
}
vec3 chromaShadowDirection(ivec2 pixel) {
    vec2 oct = (vec2(chromaShadowSeam(pixel)) + 0.5) / float(CHROMA_SHADOW_RES) * 2.0 - 1.0;
    vec3 direction = vec3(oct, 1.0 - abs(oct.x) - abs(oct.y));
    if (direction.z < 0.0)
        direction.xy = (1.0 - abs(direction.yx)) * mix(vec2(-1), vec2(1), greaterThanEqual(direction.xy, vec2(0)));
    return normalize(direction);
}
// Broad kernels use radial-depth PCSS. Subtexel kernels additionally resolve
// one physical ray against cached finite surfaces so map texels cannot fill
// alpha holes. Both paths remain limited by observed/cached geometry.
const float CHROMA_PCSS_MAX_SLOPE = 1.0;
const float CHROMA_PCSS_MAX_RADIAL_BIAS = 0.05;

void chromaPcssBasis(vec3 axis, out vec3 tangent, out vec3 bitangent) {
    // Frisvad's frame is continuous away from its south-pole singularity;
    // unlike a .9 axis switch, ordinary source motion cannot rotate the disk.
    if (axis.z < -0.9999999) tangent = normalize(vec3(0.0, -axis.z, axis.y));
    else {
        float a = 1.0 / (1.0 + axis.z);
        tangent = normalize(vec3(1.0 - axis.x * axis.x * a,
                                 -axis.x * axis.y * a, -axis.x));
    }
    bitangent = cross(axis, tangent);
}
float chromaPcssTexelSlope(vec3 axis) {
    // Angular Jacobian of octahedral decoding at this continuous direction.
    // A texel is not 1/128 radians; its footprint varies over the octahedron.
    float scale = abs(axis.x) + abs(axis.y) + abs(axis.z);
    vec2 signs = mix(vec2(-1.0), vec2(1.0), greaterThanEqual(axis.xy, vec2(0.0)));
    vec3 dx = vec3(1.0, 0.0, -signs.x);
    vec3 dy = vec3(0.0, 1.0, -signs.y);
    if (axis.z < 0.0) {
        dx = vec3(0.0, -signs.x * signs.y, -signs.x);
        dy = vec3(-signs.x * signs.y, 0.0, -signs.y);
    }
    return min(length(dx - axis * dot(axis, dx)),
               length(dy - axis * dot(axis, dy))) * scale * (2.0 / float(CHROMA_SHADOW_RES));
}

bool chromaAreaCellBlocked(ivec3 cell, vec3 origin, vec3 direction, float distance) {
    if (!chromaVoxContains(cell, chromaVoxOrigin())) return false;
    // A zero LOD parent proves that all four surface records are empty. Most
    // candidate crossings above a lit floor take this one-fetch path.
    if (!chromaOccupiedLod(VoxelLod1Sampler, cell, 1)) return false;
    return chromaVoxDataRayAny(chromaVoxSurfaceData(VoxelSampler, cell),
                              cell, origin, direction, distance);
}
bool chromaAreaPlaneBlocked(int axis, int face, vec3 origin, vec3 direction,
                           float distance, ivec3 receiverCell) {
    if (abs(direction[axis]) < 0.000001) return false;
    float t = (float(face) * CHROMA_VOX_CELL - (origin[axis] - CameraOffset[axis])) / direction[axis];
    if (t <= 0.0 || t >= distance - 0.0001) return false;
    // The map supplies candidate cells. Dynamic intersects their observed
    // finite surface patches; Static retains its exported solid quarter cells.
    // A zero-thickness plane on a quarter-cell boundary belongs to the cell
    // inward from its acquisition normal, which can be either side of this ray.
    ivec3 before = chromaVoxOf(origin + direction * (t - 0.0001));
    ivec3 after = chromaVoxOf(origin + direction * (t + 0.0001));
    if (chromaAreaCellBlocked(before, origin, direction, distance - 0.0001)) return true;
    return any(notEqual(before, after)) && chromaAreaCellBlocked(after,
        origin, direction, distance - 0.0001);
}
// The source atlas owns the expensive depth-to-finite-surface lookup. Bit30
// selects the owner side of the quarter boundary; nonzero mask implies valid.
bool chromaAreaCachedPlane(int lamp, ivec2 pixel, vec3 light, float depth,
                           out uint surface, out vec4 plane, out ivec3 cell) {
    ivec2 tile = ivec2(lamp % 16, lamp / 16) * CHROMA_SHADOW_RES;
    uint payload = chromaVoxDecode(texelFetch(SurfaceSampler, tile + chromaShadowSeam(pixel), 0));
    if (chromaSurfelMask(payload) == 0u && (payload & 0x80000000u) == 0u) return false;
    vec3 mapDirection = chromaShadowDirection(pixel);
    light = chromaShadowMapOrigin(light);
    cell = chromaVoxOf(light + mapDirection * (depth + ((payload & 0x40000000u) != 0u ? 0.0001 : -0.0001)));
    surface = payload | 0x40000000u;
    if ((surface & 0x80000000u) != 0u) { plane = vec4(0.0); return true; }
    vec3 normal = chromaSurfelNormal(surface);
    float offset = (float((surface >> 8u) & 63u) / 63.0 - 0.5)
                 * CHROMA_VOX_CELL * dot(abs(normal), vec3(1.0));
    plane = vec4(normal, dot(normal, chromaVoxCentre(cell)) + offset);
    return true;
}
bool chromaAreaSamePlane(vec4 a, ivec3 aCell, vec4 b, ivec3 bCell) {
    if (dot(a.xyz, a.xyz) < 0.5 || dot(b.xyz, b.xyz) < 0.5)
        return dot(a.xyz, a.xyz) < 0.5 && dot(b.xyz, b.xyz) < 0.5 && all(equal(aCell, bCell));
    float facing = dot(a.xyz, b.xyz);
    return abs(facing) > 0.99999 && abs(a.w - (facing < 0.0 ? -b.w : b.w)) < 0.00001;
}
bool chromaAreaProjectedBlocked(uint surface, vec4 plane, ivec3 guideCell,
                                vec3 origin, vec3 direction, float distance) {
    if (dot(plane.xyz, plane.xyz) < 0.5) {
        ivec3 localCell = guideCell - CameraBlockPos * CHROMA_VOX_CELLS;
        for (int side = 0; side < 2; ++side) {
            ivec3 face = localCell + (side == 0 ? ivec3(lessThan(direction, vec3(0.0)))
                : ivec3(greaterThanEqual(direction, vec3(0.0))));
            for (int axis = 0; axis < 3; ++axis)
                if (chromaAreaPlaneBlocked(axis, face[axis], origin, direction, distance, ivec3(0))) return true;
        }
        return false;
    }
    float denominator = dot(plane.xyz, direction);
    if (abs(denominator) < 0.0000001) return false;
    float t = (plane.w - dot(plane.xyz, origin)) / denominator;
    if (t <= 0.0 || t >= distance - 0.0001) return false;
    vec3 hit = origin + direction * t;
    ivec3 before = chromaVoxOf(origin + direction * (t - 0.0001));
    ivec3 after = chromaVoxOf(origin + direction * (t + 0.0001));
    if ((all(equal(before, guideCell)) || all(equal(after, guideCell)))
            && chromaSurfelCoveredAxis(surface, guideCell, hit, chromaSurfelAxis(plane.xyz))) return true;
    // An infinite guide plane is only a candidate. Validate its actual owner
    // cell, so a distant wall remains continuous without filling alpha holes.
    if (chromaAreaCellBlocked(before, origin, direction, distance - 0.0001)) return true;
    return any(notEqual(before, after)) && chromaAreaCellBlocked(after, origin, direction, distance - 0.0001);
}
float chromaPcssHardShadow(int lamp, vec3 receiver, vec3 normal, vec3 light,
                           float normalBias, float lightRadius, float sourceRadius) {
    vec3 target = receiver + normal * normalBias;
    vec3 delta = target - light;
    float distance = length(delta);
    if (distance <= 0.00001) return 1.0;
    vec3 axis = delta / distance;
    vec3 tangent, bitangent;
    chromaPcssBasis(axis, tangent, bitangent);
    float searchAngle = min(sourceRadius / max(0.5, distance * 0.2), CHROMA_PCSS_MAX_SLOPE);
    int seedCount = 0;
    ivec3 seedCells[4];
    vec4 seedPlanes[4];
    uint seedSurfaces[4];
    // At most seventeen depth seeds and four distinct finite guide planes.
    for (int i = 0; i < 9; ++i) {
        vec2 offset = CHROMA_SEARCH_DISK[i] * searchAngle;
        vec3 ray = normalize(axis + tangent * offset.x + bitangent * offset.y);
        ivec2 middle = ivec2(floor(chromaShadowUV(ray) * float(CHROMA_SHADOW_RES)));
        for (int j = 0; j < (i == 0 ? 9 : 1); ++j) {
            ivec2 pixel = middle + (i == 0 ? CHROMA_BLOCKER_OFFSETS[j] : ivec2(0));
            float depth = chromaShadowDepth(lamp, pixel);
            if (!(depth > 0.0001) || depth >= lightRadius - 0.001
                    || depth > distance + sourceRadius) continue;
            vec3 hit = light + chromaShadowDirection(pixel) * (depth + 0.0001);
            if (dot(hit - receiver, normal) <= 0.0) continue;
            vec4 plane; ivec3 cell; uint surface;
            if (!chromaAreaCachedPlane(lamp, pixel, light, depth, surface, plane, cell)) continue;
            bool duplicate = false;
            for (int previous = 0; previous < seedCount; ++previous)
                duplicate = duplicate || chromaAreaSamePlane(plane, cell, seedPlanes[previous], seedCells[previous]);
            if (!duplicate && seedCount < 4) {
                seedSurfaces[seedCount] = surface; seedPlanes[seedCount] = plane; seedCells[seedCount++] = cell;
            }
        }
    }
    // One central segment, not the old sixteen source-disk geometry traces.
    // Check the start cell too: an inset source can hit a patch before a face.
    if (chromaAreaCellBlocked(chromaVoxOf(light), light, axis, distance - 0.0001)) return 0.0;
    for (int seed = 0; seed < seedCount; ++seed)
        if (chromaAreaProjectedBlocked(seedSurfaces[seed], seedPlanes[seed], seedCells[seed],
                                      light, axis, distance)) return 0.0;
    return 1.0;
}

float chromaPcssReceiverDepth(vec3 ray, vec3 normal, float plane) {
    float denominator = dot(ray, normal);
    // A ray in the other hemisphere never reaches this receiving plane.
    if (abs(denominator) < 0.00001 || denominator * plane <= 0.0) return -1.0;
    return plane / denominator;
}
float chromaPcssBias(vec3 ray, vec3 normal, float normalBias) {
    // Convert the bounded surface-normal allowance to radial depth, then cap
    // it again: grazing angles must not create an arbitrarily large light leak.
    return min(normalBias / max(abs(dot(ray, normal)), 0.00001),
               CHROMA_PCSS_MAX_RADIAL_BIAS);
}
bool chromaPcssHasBlocker(float depth, float radius) {
    // Radius is the no-hit sentinel. Comparisons also reject NaN/Inf/negative
    // payloads; zero remains a real embedded-source hit, not empty space.
    return depth >= 0.0 && depth < radius - 0.001;
}
vec2 chromaPcssCompare(int lamp, vec3 direction, vec3 normal, float plane,
                      float normalBias, float lightRadius) {
    vec2 p = chromaShadowUV(direction) * float(CHROMA_SHADOW_RES) - 0.5;
    ivec2 base = ivec2(floor(p));
    vec2 fraction = fract(p);
    vec2 result = vec2(0.0);
    // Packed float depth cannot use hardware linear filtering. Interpolate
    // four COMPARISONS, each at its own texel ray/receiver-plane intersection.
    // Averaging depths first creates nonexistent surfaces across silhouettes.
    for (int i = 0; i < 4; ++i) {
        ivec2 offset = ivec2(i & 1, i >> 1);
        vec2 weight2 = mix(1.0 - fraction, fraction, bvec2(offset));
        float weight = weight2.x * weight2.y;
        if (weight <= 0.0) continue;
        ivec2 pixel = base + offset;
        vec3 ray = chromaShadowDirection(pixel);
        float receiverDepth = chromaPcssReceiverDepth(ray, normal, plane);
        if (receiverDepth <= 0.0) continue;
        float depth = chromaShadowDepth(lamp, pixel);
        float bias = min(chromaPcssBias(ray, normal, normalBias), receiverDepth * 0.5);
        bool blocked = chromaPcssHasBlocker(depth, lightRadius) && depth < receiverDepth - bias;
        result += vec2(blocked ? 0.0 : weight, weight);
    }
    return result;
}
float chromaPcssVisibility(vec2 comparison) {
    return comparison.y > 0.000001 ? clamp(comparison.x / comparison.y, 0.0, 1.0) : 1.0;
}
float chromaShadow(int lamp, vec3 receiver, vec3 normal, vec3 light, float lightRadius) {
    if (!(lightRadius > 0.0) || isinf(lightRadius)) return 1.0;
    light = chromaShadowMapOrigin(light);
    vec3 delta = receiver - light;
    float distance = length(delta);
    float normalLength2 = dot(normal, normal);
    if (!(distance > 0.00001) || isinf(distance)
            || !(normalLength2 > 0.00000001) || isinf(normalLength2)) return 1.0;
    normal *= inversesqrt(normalLength2);
    float plane = dot(delta, normal);
    float height = -plane;
    // shade.fsh already skips back-facing receivers. Keep a neutral result
    // for invalid/direct calls instead of dividing through a tangent plane.
    if (!(height > 0.000001)) return 1.0;
    float quantizationBias = max(abs(normal.x), max(abs(normal.y), abs(normal.z))) > 0.99999
        ? 0.005 : 0.035;
    float normalBias = min(quantizationBias, height * 0.5);
    vec3 axis = delta / distance;
    ivec2 centerPixel = ivec2(floor(chromaShadowUV(axis) * float(CHROMA_SHADOW_RES)));
    float centerDepth = chromaShadowDepth(lamp, centerPixel);
    // Preserve the previous conservative embedded-centre behavior. Off-centre
    // emitter occlusion cannot be reconstructed from a single centre depth map.
    if (centerDepth >= 0.0 && centerDepth <= 0.0001) return 0.0;
    float sourceRadius = max(CHROMA_SOURCE_SIZE, 0.0);
    if (sourceRadius <= 0.000001)
        return chromaPcssHardShadow(lamp, receiver, normal, light, normalBias, lightRadius, sourceRadius);
    vec3 tangent, bitangent;
    chromaPcssBasis(axis, tangent, bitangent);
    // Seventeen bounded reads: a continuous local 3x3 tent plus eight wider
    // probes. This finite search can miss a thin blocker between its samples.
    float searchAngle = min(sourceRadius / max(0.5, distance * 0.2), CHROMA_PCSS_MAX_SLOPE);
    float blockerSum = 0.0, blockerWeight = 0.0;
    for (int i = 0; i < 9; ++i) {
        vec2 offset = CHROMA_SEARCH_DISK[i] * searchAngle;
        vec3 direction = normalize(axis + tangent * offset.x + bitangent * offset.y);
        vec2 p = chromaShadowUV(direction) * float(CHROMA_SHADOW_RES) - 0.5;
        ivec2 middle = ivec2(floor(p + 0.5));
        vec2 normalization = 2.5 - abs(p - vec2(middle));
        for (int j = 0; j < (i == 0 ? 9 : 1); ++j) {
            ivec2 pixel = middle + (i == 0 ? CHROMA_BLOCKER_OFFSETS[j] : ivec2(0));
            vec2 weight2 = max(vec2(1.5) - abs(vec2(pixel) - p), vec2(0.0));
            float weight = i == 0 ? weight2.x * weight2.y / (normalization.x * normalization.y) : 1.0;
            if (weight <= 0.0) continue;
            vec3 ray = chromaShadowDirection(pixel);
            float receiverDepth = chromaPcssReceiverDepth(ray, normal, plane);
            if (receiverDepth <= 0.0) continue;
            float depth = chromaShadowDepth(lamp, pixel);
            float bias = min(chromaPcssBias(ray, normal, normalBias), receiverDepth * 0.5);
            if (!chromaPcssHasBlocker(depth, lightRadius) || depth >= receiverDepth - bias) continue;
            // The disk formula uses depth along the central light/receiver
            // axis, not the longer radial distance of an off-centre map ray.
            float axialDepth = depth * dot(ray, axis);
            if (axialDepth <= 0.0001 || axialDepth >= distance) continue;
            blockerSum += axialDepth * weight;
            blockerWeight += weight;
        }
    }
    if (blockerWeight <= 0.000001)
        return chromaPcssHardShadow(lamp, receiver, normal, light, normalBias, lightRadius, sourceRadius);
    float blocker = blockerSum / blockerWeight;
    // Similar triangles: R * (receiver - blocker) / (receiver * blocker).
    // Contact uses the central finite-surface ray. No minimum blur is added.
    // The slope cap bounds near-emitter kernels, not their GPU timing.
    float filterAngle = min(sourceRadius * max(distance - blocker, 0.0)
        / max(distance * blocker, 0.0001), CHROMA_PCSS_MAX_SLOPE);
    float texelSlope = chromaPcssTexelSlope(axis);
    float softWeight = smoothstep(0.5 * texelSlope, texelSlope, filterAngle);
    float hardVisibility = 1.0;
    if (softWeight < 1.0) {
        hardVisibility = chromaPcssHardShadow(lamp, receiver, normal, light, normalBias, lightRadius, sourceRadius);
        if (softWeight <= 0.0) return hardVisibility;
    }
    vec2 visible = vec2(0.0);
    for (int i = 0; i < CHROMA_SHADOW_SAMPLES; ++i) {
        vec2 disk = CHROMA_SOURCE_DISK[i];
        vec3 sourceOffset = (tangent * disk.x + bitangent * disk.y) * sourceRadius;
        // Only the physical emitter disk's front hemisphere contributes to an
        // opaque receiver. Normalize by supported comparison weights below.
        if (dot(light + sourceOffset - receiver, normal) <= 0.0) continue;
        vec3 direction = normalize(axis + (tangent * disk.x + bitangent * disk.y) * filterAngle);
        visible += chromaPcssCompare(lamp, direction, normal, plane, normalBias, lightRadius);
    }
    return mix(hardVisibility, chromaPcssVisibility(visible), softWeight);
}
#endif
#endif
