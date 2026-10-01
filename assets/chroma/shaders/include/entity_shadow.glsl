#ifndef CHROMA_ENTITY_SHADOW
#define CHROMA_ENTITY_SHADOW
#if !CHROMA_STATIC_WORLD && CHROMA_ENTITY_SHADOWS == 2 && CHROMA_TRANSPARENT_DEPTH_MASK
bool chromaEntityShadowTag(float alpha) {
    return int(floor(alpha * 255.0 + 0.5)) == 1;
}
// -1: inaccessible; 0: no scene evidence; 1: visible native-depth sample.
int chromaEntityProbe(vec4 clip, ivec2 size, out vec3 projected,
                      out ivec2 pixel, out float depth) {
    // Native projection includes bob/translation and its actual near plane.
    if (any(isnan(clip)) || any(isinf(clip)) || clip.w <= 0.000001
            || clip.z <= 0.0 || clip.z >= clip.w) return -1;
    projected = vec3(clip.xy / clip.w * 0.5 + 0.5, clip.z / clip.w);
    if (any(lessThan(projected.xy, vec2(0.0)))
            || any(greaterThanEqual(projected.xy, vec2(1.0)))) return -1;
    pixel = ivec2(floor(projected.xy * vec2(size)));
    if (chromaAutoHeaderPixel(pixel, size)) return 0;
    depth = texelFetch(InDepthSampler, pixel, 0).r;
    if (depth <= 0.000001) return 0;
    if (isnan(depth) || isinf(depth)) return -1;
    if (depth >= 0.999999) {
        // Valid current-frame packets are rasterized at clip z=w (depth1).
        // Cleared packet depth0 already returned above; ordinary scene probes
        // do not need a catalog fetch. Keep HUD/OIT unknown rather than solid.
        return chromaCatalogHas(CatalogSampler, chromaRawAddressAtPixel(pixel, size)) ? 0 : -1;
    }
    return 1;
}
// Negative means no validated entity hit. A sign crossing alone is insufficient:
// alpha silhouettes/discontinuities must still pass exact pixel tag/thickness.
float chromaEntityHit(vec3 projected, ivec2 pixel, float depth, ivec2 size,
                      vec3 origin, vec3 direction, float limit, float distance,
                      float maxDistance) {
    if (depth < projected.z
            || !chromaEntityShadowTag(texelFetch(InSampler, pixel, 0).a)) return -1.0;
    vec2 centre = (vec2(pixel) + 0.5) / vec2(size);
    vec3 scene = reconstructEyePosAt(centre, depth, cameraInvProj);
    vec3 rayAtPixel = reconstructEyePosAt(centre, projected.z, cameraInvProj);
    // Reversed-Z ordering establishes a positive gap on this one projection ray.
    const float thickness = 0.15;
    float gap = length(rayAtPixel - scene);
    if (isnan(gap) || isinf(gap) || gap > thickness) return -1.0;
    float along = dot(scene - origin, direction);
    if (along <= 0.0001 || along >= limit || along >= distance - 0.0001) return -1.0;
    float edgePixels = min(min(projected.x, 1.0 - projected.x) * float(size.x),
                           min(projected.y, 1.0 - projected.y) * float(size.y));
    float edgeFade = smoothstep(0.0, 8.0, edgePixels);
    float rangeFade = 1.0 - smoothstep(0.75 * maxDistance, maxDistance, along);
    return 1.0 - edgeFade * rangeFade;
}
float chromaEntityShadow(vec3 receiver, vec3 normal, vec3 light, ivec2 size) {
    float sourceDistance = length(light - receiver);
    if (!(sourceDistance > 0.0001) || isinf(sourceDistance)) return 1.0;
    vec3 origin = receiver + normal * min(0.01, sourceDistance * 0.1);
    vec3 segment = light - origin;
    float distance = length(segment);
    if (!(distance > 0.0001) || isinf(distance)) return 1.0;
    vec3 direction = segment / distance;
    float maxDistance = max(CHROMA_ENTITY_SHADOW_DISTANCE, 0.0);
    float limit = min(maxDistance, distance - 0.0001);
    if (limit <= 0.0001) return 1.0;
    const int steps = clamp(CHROMA_ENTITY_SHADOW_STEPS, 1, 24);
    // Projection is affine in ray travel, including native camera bob. Hoist
    // both matrix products instead of repeating one at every coarse/midpoint.
    vec4 clipOrigin = cameraProj * vec4(origin, 1.0);
    vec4 clipDirection = cameraProj * vec4(direction, 0.0);
    bool previousValid = false, previousBehind = false, previousEntity = false;
    float previousTravel = 0.0;
    vec3 previousProjected = vec3(0.0);
    ivec2 previousPixel = ivec2(0);
    float previousDepth = 0.0;
    int refinementBudget = 8;
    // ponytail: One bounded contact ray uses only current visible opaque depth.
    // At most two brackets with four midpoint refinements repair skipped depth
    // crossings: 24 coarse + 8 refinement probes maximum. The first bracket can
    // be a rejected silhouette entry. Silhouettes skipped by both endpoints and
    // hidden/offscreen geometry remain
    // unknown. There is no temporal cache or area-light penumbra.
    for (int i = 0; i < steps; ++i) {
        float travel = (float(i) + 0.5) * (limit / float(steps));
        vec3 projected; ivec2 pixel; float depth;
        int status = chromaEntityProbe(clipOrigin + clipDirection * travel, size, projected, pixel, depth);
        if (status < 0) return 1.0;
        if (status == 0) { previousValid = false; continue; }
        bool behind = depth >= projected.z;
        bool entity = behind && chromaEntityShadowTag(texelFetch(InSampler, pixel, 0).a);
        if (refinementBudget >= 4 && previousValid && behind != previousBehind && (entity || previousEntity)) {
            refinementBudget -= 4;
            float behindTravel = behind ? travel : previousTravel;
            float frontTravel = behind ? previousTravel : travel;
            vec3 hitProjected = behind ? projected : previousProjected;
            ivec2 hitPixel = behind ? pixel : previousPixel;
            float hitDepth = behind ? depth : previousDepth;
            bool validBracket = true;
            for (int refine = 0; refine < 4; ++refine) {
                float middle = 0.5 * (behindTravel + frontTravel);
                vec3 probeProjected; ivec2 probePixel; float probeDepth;
                int probeStatus = chromaEntityProbe(clipOrigin + clipDirection * middle, size,
                    probeProjected, probePixel, probeDepth);
                if (probeStatus != 1) { validBracket = false; break; }
                if (probeDepth >= probeProjected.z) {
                    behindTravel = middle;
                    hitProjected = probeProjected; hitPixel = probePixel; hitDepth = probeDepth;
                } else frontTravel = middle;
            }
            if (validBracket) {
                float hit = chromaEntityHit(hitProjected, hitPixel, hitDepth, size,
                    origin, direction, limit, distance, maxDistance);
                if (hit >= 0.0) return hit;
            }
        }
        if (behind) {
            // Ordinary foreground geometry hides later screen evidence. It is
            // not a new screen caster: retain the world filter's visibility.
            if (!entity) return 1.0;
            float hit = chromaEntityHit(projected, pixel, depth, size,
                origin, direction, limit, distance, maxDistance);
            if (hit >= 0.0) return hit;
        }
        previousValid = true; previousBehind = behind; previousEntity = entity;
        previousTravel = travel; previousProjected = projected;
        previousPixel = pixel; previousDepth = depth;
    }
    return 1.0;
}
#endif
#endif
