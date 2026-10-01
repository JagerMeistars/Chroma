#version 450
#extension GL_ARB_separate_shader_objects : require
#include <minecraft:globals.glsl>
#include <chroma:lighting.glsl>
#include <chroma:auto_read.glsl>
#include <chroma:voxel_space.glsl>
uniform sampler2D InDepthSampler;
#if !CHROMA_STATIC_WORLD && (CHROMA_PARTICLE_DEPTH_MASK || (CHROMA_ENTITY_SHADOWS != 1 && CHROMA_TRANSPARENT_DEPTH_MASK))
uniform sampler2D MainColorSampler;
#endif
uniform sampler2D CatalogSampler;
layout(location = 0) flat in int cameraValid;
layout(location = 5) flat in mat4 cameraInvProj;
layout(location = 9) flat in mat3 cameraRot;
layout(location = 0) out vec4 fragColor;
#include <chroma:depth_support.glsl>

void main() {
    // This screen-sized cache is rebuilt completely before acquisition. A
    // rejected pixel must not retain an earlier frame's native surface normal.
    fragColor = vec4(0.0);
    if (cameraValid == 0) return;
    ivec2 p = ivec2(gl_FragCoord.xy);
    ivec2 size = textureSize(InDepthSampler, 0);
    if (!evidencePixel(p, size)) return;
    float depth = texelFetch(InDepthSampler, p, 0).r;
    if (!(depth > 0.000001 && depth < 0.999999)) return;
    vec3 surface = eyeAt(p, depth, cameraInvProj, size);
    vec3 side[4], normalEye, normal, supportedNormal;
    float distanceZ[4];
    if (!depthNormal(p, surface, cameraInvProj, cameraRot, size,
                     normalEye, normal, supportedNormal, side, distanceZ)) return;
    fragColor = chromaVoxEncode(chromaDepthNormalEncode(normal,
        dot(supportedNormal, supportedNormal) > 0.5));
}
