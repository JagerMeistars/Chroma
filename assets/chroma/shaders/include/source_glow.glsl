#ifndef CHROMA_SOURCE_GLOW
#define CHROMA_SOURCE_GLOW
#include <chroma:settings.glsl>

float chromaSourceGlow(vec3 light, float lightRadius, vec3 viewRay, float sceneDistance) {
#if !CHROMA_GLOW_ENABLED
    return 0.0;
#else
    float radius = min(lightRadius, max(CHROMA_GLOW_RADIUS, 0.0));
    vec3 relativeLight = light - cameraRayOrigin;
    float cameraDistance = length(relativeLight);
    float alongRay = dot(relativeLight, viewRay);
    // Keep the halo behind foreground geometry and outside the camera itself.
    if (radius <= 0.0 || alongRay <= 0.0 || sceneDistance + 0.002 < alongRay) return 0.0;
    // Fade before the camera enters the core, avoiding a full-screen flash.
    float cameraFade = smoothstep(radius, radius * 2.0, cameraDistance);
    if (cameraFade <= 0.0) return 0.0;
    vec3 perpendicular = relativeLight - viewRay * alongRay;
    float r2 = dot(perpendicular, perpendicular) / (radius * radius);
    if (r2 >= 1.0) return 0.0;

    // Checking only each halo pixel would leave glow around a wall edge even
    // when the source itself is hidden. Require a visible source centre too.
    vec4 clip = cameraProj * vec4(light, 1.0);
    if (clip.w <= 0.0001) return 0.0;
    vec2 centreUV = clip.xy / clip.w * 0.5 + 0.5;
    if (any(lessThan(centreUV, vec2(0.0))) || any(greaterThanEqual(centreUV, vec2(1.0)))) return 0.0;
    ivec2 size = textureSize(InDepthSampler, 0);
    // Offscreen centre occlusion is unknown; fade at the border before culling.
    vec2 edgePixels = min(centreUV, vec2(1.0) - centreUV) * vec2(size);
    float edgeFade = smoothstep(0.0, 4.0, min(edgePixels.x, edgePixels.y));
    ivec2 pixel = ivec2(centreUV * vec2(size));
    int cleanY = chromaSceneCleanY(pixel, size);
    if (cleanY >= 0) pixel.y = cleanY;
    float depth = texelFetch(InDepthSampler, pixel, 0).r;
    // HUD/translucency uses this sentinel: its opaque background depth is lost.
    // Fail closed instead of drawing glow through an unknown wall.
    if (depth >= 0.999999) return 0.0;
    if (depth > 0.000001) {
        vec2 sampleUV = (vec2(pixel) + 0.5) / vec2(size);
        vec3 occluder = reconstructEyePosAt(sampleUV, depth, cameraInvProj);
        float occluderDistance = dot(occluder - cameraRayOrigin, relativeLight / cameraDistance);
        if (occluderDistance + 0.002 < cameraDistance) return 0.0;
    }
    // Compact support: no contribution outside the small source radius.
    float falloff = 1.0 - r2;
    falloff = falloff * falloff * falloff;
    // Scale the soft transition around its current midpoint. At softness 1.0
    // the delta is exactly zero, preserving the approved edge and brightness.
    float edgeDelta = 0.225344162 * (clamp(CHROMA_GLOW_SOFTNESS, 0.01, 2.0) - 1.0);
    falloff = smoothstep(0.268882764 - edgeDelta, 0.719571088 + edgeDelta, falloff);
    return max(CHROMA_GLOW_STRENGTH, 0.0) * cameraFade * edgeFade * falloff;
#endif
}
#endif
