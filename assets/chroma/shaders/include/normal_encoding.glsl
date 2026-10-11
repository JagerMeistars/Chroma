#ifndef CHROMA_NORMAL_ENCODING
#define CHROMA_NORMAL_ENCODING
#include <chroma:normal_config.glsl>

// A camera-independent basis for the small material perturbation. The depth
// normal remains the surface normal used by the voxel cache and shadow rays.
mat3 chromaNormalBasis(vec3 n) {
    vec3 axis = abs(n.y) < 0.999 ? vec3(0.0, 1.0, 0.0) : vec3(1.0, 0.0, 0.0);
    vec3 t = normalize(cross(axis, n));
    return mat3(t, cross(n, t), n);
}

float chromaEncodeMaterialNormal(vec3 n, vec3 detail) {
    vec3 local = transpose(chromaNormalBasis(n)) * detail;
    vec2 slope = clamp(local.xy / max(local.z, 0.05), vec2(-1.0), vec2(1.0));
    ivec2 q = ivec2(floor(slope * 7.0 + 7.5));
    // 0 and 1 are existing particle/entity tags; 255 is an ordinary surface.
    return float(2 + q.x + 15 * q.y) / 255.0;
}

vec3 chromaDecodeMaterialNormal(float alpha, vec3 geometricNormal) {
#if CHROMA_NORMAL_MAPS
    int code = int(alpha * 255.0 + 0.5) - 2;
    if (code >= 0 && code < 225) {
        vec2 slope = (vec2(code % 15, code / 15) - 7.0) / 7.0;
        return normalize(chromaNormalBasis(geometricNormal) *
            vec3(slope * CHROMA_NORMAL_STRENGTH, 1.0));
    }
#endif
    return geometricNormal;
}
#endif
