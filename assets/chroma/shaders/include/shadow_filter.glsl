#ifndef CHROMA_SHADOW_FILTER
#define CHROMA_SHADOW_FILTER
#include <chroma:voxel_space.glsl>
uniform sampler2D ShadowSampler;
uniform sampler2D VoxelSampler;
const int CHROMA_SHADOW_RES = 128;

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
float chromaReceiverDepth(vec3 direction, vec3 normal, float plane) {
    float denominator = dot(direction, normal);
    if (abs(denominator) < 0.0001 || denominator * plane <= 0.0) return 1e6;
    return plane / denominator;
}
bool chromaShadowReceiverHit(float surfaceOffset, float receiverBias) {
    // A conservative voxel face may sit above the true slab/sloped surface.
    // Recognize only the hull already crossed by the normal bias, not an
    // arbitrary full voxel; otherwise a clear receiver shadows itself.
    return surfaceOffset >= -0.02 && surfaceOffset <= receiverBias + 0.02;
}
float chromaShadowRayDepth(int lamp, vec3 direction, vec3 light, float lightRadius) {
    vec2 p = chromaShadowUV(direction) * float(CHROMA_SHADOW_RES) - 0.5;
    ivec2 base = ivec2(floor(p));
    vec3 localLight = light - CameraOffset;
    float nearest = lightRadius;
    ivec3 seen = ivec3(2147483647);
    // Each stored DDA hit lies on a quarter-cell face. Reproject that face
    // onto the requested ray and check the actual voxel there. Bilinear
    // comparison of four unrelated rays made a straight silhouette sawtoothed.
    // This uses the existing map as four geometric candidates, not four binary
    // coverage samples; no longer ray march or higher-resolution map is needed.
    for (int i = 0; i < 4; ++i) {
        ivec2 pixel = base + ivec2(i & 1, i >> 1);
        float depth = chromaShadowDepth(lamp, pixel);
        if (depth <= 0.0001) return depth;
        if (depth >= lightRadius - 0.001) continue;
        vec3 sampledDirection = chromaShadowDirection(pixel);
        vec3 hit = localLight + sampledDirection * depth;
        ivec3 face = ivec3(round(hit * float(CHROMA_VOX_CELLS)));
        vec3 plane = vec3(face) * CHROMA_VOX_CELL;
        for (int axis = 0; axis < 3; ++axis) {
            // Skip tangent coordinates that merely happen to lie on a grid
            // plane. At genuine edge/corner ties, try each crossed face.
            if (abs(hit[axis] - plane[axis]) > 0.002
                    || abs(sampledDirection[axis]) < 0.000001
                    || abs(direction[axis]) < 0.000001
                    || seen[axis] == face[axis]) continue;
            seen[axis] = face[axis];
            float t = (plane[axis] - localLight[axis]) / direction[axis];
            if (t <= 0.0 || t >= nearest) continue;
            ivec3 cell = chromaVoxOf(light + direction * (t + 0.0001));
            if (chromaVoxConfidence(VoxelSampler, cell) >= 2u) nearest = t;
        }
    }
    return nearest;
}
vec2 chromaShadowPCF(int lamp, vec3 direction, vec3 light, vec3 normal, float surfacePlane, float distance,
                     float footprint, float lightRadius, float receiverBias, float foregroundLimit) {
    float depth = chromaShadowRayDepth(lamp, direction, light, lightRadius);
    float reference = chromaReceiverDepth(direction, normal, surfacePlane + receiverBias);
    // An empty ray that never reaches this plane inside the source range is
    // not a clear receiver sample. Counting it lit leaks through a nearby slab.
    if (depth >= lightRadius - 0.001)
        return reference <= lightRadius ? vec2(1.0) : vec2(0.0);
    if (chromaShadowReceiverHit(dot(direction, normal) * depth - surfacePlane, receiverBias)) {
        // The sampled receiver surface is clear, but an earlier intersection
        // with its infinite plane says nothing about blockers farther along
        // the central ray. Fade those foreground samples out continuously.
        // Hard footprint rejection caused full lit/dark jumps on straight edges.
        float weight = smoothstep(foregroundLimit, foregroundLimit + footprint, depth);
        return vec2(weight);
    }
    // Preserve plane-relative comparison for nearby parallel blockers. A
    // grazing intersection before the receiver cannot prove the rest is clear.
    reference = reference > 1e5 ? distance : max(distance, reference);
    return vec2(step(reference - 0.02, depth), 1.0);
}
float chromaShadowFallbackDepth(int lamp, ivec2 pixel, vec3 normal, float plane, float lightRadius) {
    float depth = chromaShadowDepth(lamp, pixel);
    if (depth >= lightRadius - 0.001) return depth;
    float reference = chromaReceiverDepth(chromaShadowDirection(pixel), normal, plane);
    // A texel consistent with the extrapolated receiver plane is its own
    // surface, not evidence of a separate blocker along the central ray.
    return reference < 1e5 && depth >= reference - 0.02 ? -1.0 : depth;
}
float chromaShadowFallback(int lamp, vec3 axis, vec3 normal, float plane, float distance, float lightRadius) {
    // Near the plane horizon, even adjacent texels may project far from the
    // receiver. Use the least-occluding local radial depth in this finite-map
    // case, instead of declaring the absent plane samples fully illuminated.
    ivec2 p = ivec2(floor(chromaShadowUV(axis) * float(CHROMA_SHADOW_RES) - 0.5));
    float depth = max(max(chromaShadowFallbackDepth(lamp, p, normal, plane, lightRadius),
                          chromaShadowFallbackDepth(lamp, p + ivec2(1,0), normal, plane, lightRadius)),
                      max(chromaShadowFallbackDepth(lamp, p + ivec2(0,1), normal, plane, lightRadius),
                          chromaShadowFallbackDepth(lamp, p + ivec2(1,1), normal, plane, lightRadius)));
    return depth < 0.0 || depth >= lightRadius - 0.001 ? 1.0 : step(distance - 0.02, depth);
}
float chromaShadow(int lamp, vec3 receiver, vec3 normal, vec3 light, float lightRadius) {
#if CHROMA_STATIC_WORLD
    float bias = 0.035;
#else
    float bias = 0.18;
#endif
    // Never move the receiver plane onto/across its source. At plane == 0,
    // the old blocker search rejected every tap and returned fully lit.
    float height = max(dot(light - receiver, normal), 0.0);
    float surfacePlane = dot(receiver - light, normal);
    float receiverBias = min(bias, height * 0.5);
    receiver += normal * receiverBias;
    vec3 delta = receiver - light;
    float distance = length(delta);
    if (distance < 0.05) return 1.0;
    vec3 axis = delta / distance;
    ivec2 centerPixel = ivec2(chromaShadowUV(axis) * float(CHROMA_SHADOW_RES));
    float centerDepth = chromaShadowDepth(lamp, centerPixel);
    // The DDA's occupied start cell returns 0.000025 blocks. Such an origin
    // hit is occlusion, not an empty map or a missing blocker-search sample.
    if (centerDepth <= 0.0001) return 0.0;
    vec3 tangent = normalize(cross(axis, abs(axis.y) < 0.9 ? vec3(0,1,0) : vec3(1,0,0)));
    vec3 bitangent = cross(axis, tangent);
    float plane = dot(delta, normal);
    float blockerSum = 0.0, blockers = 0.0, farthestBlocker = 0.0;
    float searchAngle = CHROMA_SOURCE_SIZE / max(0.5, distance * 0.2);
    float texelFootprint = distance * (4.0 / float(CHROMA_SHADOW_RES));
    for (int i = 0; i < 9; ++i) {
        float angle = float(i) * 2.39996323;
        float radius = i == 0 ? 0.0 : sqrt(float(i) / 8.0) * searchAngle;
        vec3 ray = normalize(axis + radius * (cos(angle) * tangent + sin(angle) * bitangent));
        ivec2 pixel = ivec2(chromaShadowUV(ray) * float(CHROMA_SHADOW_RES));
        float depth = i == 0 ? centerDepth : chromaShadowDepth(lamp, pixel);
        float surfaceOffset = dot(chromaShadowDirection(pixel), normal) * depth - surfacePlane;
        if (!chromaShadowReceiverHit(surfaceOffset, receiverBias) && depth > 0.0001 && depth < lightRadius - 0.001 && depth < distance - 0.02) {
            blockerSum += depth; blockers += 1.0;
            farthestBlocker = max(farthestBlocker, depth);
        }
    }
    if (blockers == 0.0) {
        vec2 center = chromaShadowPCF(lamp, axis, light, normal, surfacePlane, distance, texelFootprint, lightRadius, receiverBias, distance);
        return center.y > 0.00001 ? center.x / center.y : chromaShadowFallback(lamp, axis, normal, plane, distance, lightRadius);
    }
    float blocker = blockerSum / blockers;
    float penumbra = CHROMA_SOURCE_SIZE * max(distance - blocker, 0.0)
                   / max(distance * blocker, 0.01);
    // Geometric samples across a source-sized disk, all in world directions.
    float filterAngle = max(penumbra, 0.7 / float(CHROMA_SHADOW_RES));
    float footprint = distance * filterAngle + texelFootprint;
    // A receiver-plane hit beyond the local blockers is useful lit evidence,
    // even if its radial distance is shorter than the central receiver's.
    // Requiring the full distance overdarkened and displaced straight edges.
    // Keep the source-side half excluded: a wide near-source filter can see
    // foreground plane intersections that hide an otherwise closed wall.
    float foregroundLimit = max(distance * 0.5,
        min(distance, farthestBlocker + texelFootprint));
    vec2 visible = vec2(0.0);
    for (int i = 0; i < 16; ++i) {
        float angle = float(i) * 2.39996323;
        float radius = sqrt((float(i) + 0.5) / 16.0) * filterAngle;
        vec3 ray = normalize(axis + radius * (cos(angle) * tangent + sin(angle) * bitangent));
        visible += chromaShadowPCF(lamp, ray, light, normal, surfacePlane, distance, footprint, lightRadius, receiverBias, foregroundLimit);
    }
    return visible.y > 0.00001 ? visible.x / visible.y : chromaShadowFallback(lamp, axis, normal, plane, distance, lightRadius);
}
#endif
