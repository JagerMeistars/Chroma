#ifndef CHROMA_SHADOW_FILTER
#define CHROMA_SHADOW_FILTER
#include <chroma:voxel_space.glsl>
uniform sampler2D ShadowSampler;
const int CHROMA_SHADOW_RES = 128;

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
float chromaShadowCompare(int lamp, ivec2 pixel, vec3 normal, float plane, float lightRadius) {
    float reference = chromaReceiverDepth(chromaShadowDirection(pixel), normal, plane) - 0.02;
    float depth = chromaShadowDepth(lamp, pixel);
    return reference > 1e5 || depth >= lightRadius - 0.001 ? 1.0 : step(reference, depth);
}
float chromaShadowPCF(int lamp, vec3 direction, vec3 normal, float plane, float lightRadius) {
    vec2 p = chromaShadowUV(direction) * float(CHROMA_SHADOW_RES) - 0.5;
    ivec2 base = ivec2(floor(p));
    vec2 w = fract(p);
    vec4 visible = vec4(
        chromaShadowCompare(lamp, base, normal, plane, lightRadius),
        chromaShadowCompare(lamp, base + ivec2(1,0), normal, plane, lightRadius),
        chromaShadowCompare(lamp, base + ivec2(0,1), normal, plane, lightRadius),
        chromaShadowCompare(lamp, base + ivec2(1,1), normal, plane, lightRadius));
    return mix(mix(visible.x, visible.y, w.x), mix(visible.z, visible.w, w.x), w.y);
}
float chromaShadow(int lamp, vec3 receiver, vec3 normal, vec3 light, float lightRadius) {
#if CHROMA_STATIC_WORLD
    receiver += normal * 0.035;
#else
    receiver += normal * 0.18;
#endif
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
    float blockerSum = 0.0, blockers = 0.0;
    float searchAngle = CHROMA_SOURCE_SIZE / max(0.5, distance * 0.2);
    for (int i = 0; i < 9; ++i) {
        float angle = float(i) * 2.39996323;
        float radius = i == 0 ? 0.0 : sqrt(float(i) / 8.0) * searchAngle;
        vec3 ray = normalize(axis + radius * (cos(angle) * tangent + sin(angle) * bitangent));
        ivec2 pixel = ivec2(chromaShadowUV(ray) * float(CHROMA_SHADOW_RES));
        float depth = i == 0 ? centerDepth : chromaShadowDepth(lamp, pixel);
        float reference = chromaReceiverDepth(chromaShadowDirection(pixel), normal, plane) - 0.02;
        if (depth > 0.0001 && depth < lightRadius - 0.001 && depth < reference && reference < 1e5) {
            blockerSum += depth; blockers += 1.0;
        }
    }
    if (blockers == 0.0) return 1.0;
    float blocker = blockerSum / blockers;
    float penumbra = CHROMA_SOURCE_SIZE * max(distance - blocker, 0.0)
                   / max(distance * blocker, 0.01);
    // Bilinear comparison plus a source-sized disk, all in world directions.
    float filterAngle = max(penumbra, 0.7 / float(CHROMA_SHADOW_RES));
    float visible = 0.0;
    for (int i = 0; i < 16; ++i) {
        float angle = float(i) * 2.39996323;
        float radius = sqrt((float(i) + 0.5) / 16.0) * filterAngle;
        vec3 ray = normalize(axis + radius * (cos(angle) * tangent + sin(angle) * bitangent));
        visible += chromaShadowPCF(lamp, ray, normal, plane, lightRadius);
    }
    return visible / 16.0;
}
#endif
