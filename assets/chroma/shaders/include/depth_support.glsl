#ifndef CHROMA_DEPTH_SUPPORT
#define CHROMA_DEPTH_SUPPORT
// Callers provide InDepthSampler/CatalogSampler and conditional MainColorSampler,
// plus auto_read.glsl and voxel_space.glsl. Keep native depth support identical
// in the current-frame cache; consumers retain full-footprint vacancy proofs.
bool evidencePixel(ivec2 p, ivec2 size) {
    if (any(lessThan(p, ivec2(2))) || any(greaterThanEqual(p, size - 2))) return false;
    if (chromaAutoHeaderPixel(p, size)) return false;
    #if !CHROMA_STATIC_WORLD && (CHROMA_PARTICLE_DEPTH_MASK || (CHROMA_ENTITY_SHADOWS != 1 && CHROMA_TRANSPARENT_DEPTH_MASK))
    float metadataAlpha = texelFetch(MainColorSampler, p, 0).a;
    #if CHROMA_PARTICLE_DEPTH_MASK
    // Opaque particles preserve RGB/depth and mark only their unused alpha.
    // Sky alpha can also be zero: actual zero-depth sky remains valid vacancy.
    if (metadataAlpha < 0.5 / 255.0 &&
        texelFetch(InDepthSampler, p, 0).r > 0.000001) return false;
    #endif
    #if CHROMA_ENTITY_SHADOWS != 1 && CHROMA_TRANSPARENT_DEPTH_MASK
    // Entity depth still belongs to a receiver. It supplies neither a caster
    // nor evidence that cached geometry behind it has become empty.
    if (int(floor(metadataAlpha * 255.0 + 0.5)) == 1) return false;
    #endif
    #endif
    return !chromaCatalogHas(CatalogSampler, chromaRawAddressAtPixel(p, size));
}

vec3 eyeAt(ivec2 p, float depth, mat4 inverseProjection, ivec2 size) {
    vec2 uv = (vec2(p) + 0.5) / vec2(size);
    vec4 eye = inverseProjection * vec4(uv * 2.0 - 1.0, depth, 1.0);
    return eye.xyz / eye.w;
}

bool depthNormal(ivec2 p, vec3 surface, mat4 inverseProjection, mat3 rotation, ivec2 size,
                 out vec3 normalEye, out vec3 normal, out vec3 observedNormal,
                 out vec3 side[4], out float distanceZ[4]) {
    ivec2 px[4] = ivec2[4](p + ivec2(-1,0), p + ivec2(1,0),
                            p + ivec2(0,-1), p + ivec2(0,1));
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
    if (distanceZ[horizontal] > 1.0 || distanceZ[vertical] > 1.0) return false;
    vec3 dx = horizontal == 1 ? side[1]-surface : surface-side[0];
    vec3 dy = vertical == 3 ? side[3]-surface : surface-side[2];
    vec3 crossNormal = cross(dx, dy);
    if (dot(crossNormal, crossNormal) < 1e-16) return false;
    normalEye = normalize(crossNormal);
    if (dot(normalEye, surface) > 0.0) normalEye = -normalEye;
    // Only the selected local triangle defines this surface. Its unused
    // neighbors may be background at a fence, slab, stair, or entity silhouette.
    normal = normalize(transpose(rotation) * normalEye);
    // Preserve the unsnapped normal for bounds: tilted surfaces must not be
    // mistaken for axis-aligned box faces by the acquisition stability snap.
    observedNormal = normal;
    int axis = abs(normal.x) > abs(normal.y) ? 0 : 1;
    if (abs(normal.z) > abs(normal[axis])) axis = 2;
    // Three depth pixels always define a plane, even when they belong to
    // different faces at a thin corner. Oblique surfels need independent
    // support on both screen axes. Exact axis faces retain silhouette coverage.
    // Only the normal is withheld: a coarse positive still triggers fine probes.
    if (abs(normal[axis]) <= 0.99999) {
        for (int i = 0; i < 4; ++i)
            if (distanceZ[i] >= 1.0 || abs(dot(side[i] - surface, normalEye)) > 0.002)
                observedNormal = vec3(0.0);
    }
    return true;
}

// Octahedral 15+15 bits; codes 0..32766 include zero exactly. Flags preserve
// the original reconstruction result, including valid but unsupported normals.
uint chromaDepthNormalEncode(vec3 normal, bool supported) {
    vec3 n = normal / dot(abs(normal), vec3(1.0));
    vec2 oct = n.xy;
    if (n.z < 0.0)
        oct = (1.0 - abs(oct.yx)) * mix(vec2(-1.0), vec2(1.0), greaterThanEqual(oct, vec2(0.0)));
    uvec2 q = uvec2(clamp(floor((oct * 0.5 + 0.5) * 32766.0 + 0.5), vec2(0.0), vec2(32766.0)));
    return q.x | (q.y << 15u) | 0x40000000u | (supported ? 0x80000000u : 0u);
}
vec3 chromaDepthNormalDecode(uint word) {
    vec2 oct = vec2(word & 32767u, (word >> 15u) & 32767u) / 32766.0 * 2.0 - 1.0;
    vec3 n = vec3(oct, 1.0 - abs(oct.x) - abs(oct.y));
    if (n.z < 0.0)
        n.xy = (1.0 - abs(n.yx)) * mix(vec2(-1.0), vec2(1.0), greaterThanEqual(n.xy, vec2(0.0)));
    return normalize(n);
}
#endif
