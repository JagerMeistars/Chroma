#version 330
#extension GL_ARB_separate_shader_objects : require

#include <minecraft:fog.glsl>
#include <minecraft:globals.glsl>
#include <minecraft:texture_sampling.glsl>
#include <minecraft:oit.glsl>
#include <minecraft:terrainglobals.glsl>
#ifndef MULTIDRAW_TERRAIN
    #include <minecraft:chunksection.glsl>
#endif

#include <minecraft:projection.glsl>
#include <chroma:normal_material.glsl>

uniform sampler2D Sampler0;

layout(location = 0) in float sphericalVertexDistance;
layout(location = 1) in float cylindricalVertexDistance;
layout(location = 2) in vec4 vertexColor;
layout(location = 3) in vec2 texCoord0;
layout(location = 4) in float chunkVisibility;

#ifndef OIT_ALPHA_ONLY
layout(location = 0) out vec4 fragColor;
#endif

vec4 calculateFinalColor(vec4 color) {
    #ifdef OIT_ACCUMULATE
    color = sampleColorForAccumulation(color);
    vec4 fogColor = vec4(FogColor.rgb * color.a, FogColor.a);
    #else
    vec4 fogColor = FogColor;
    #endif
    return apply_fog(color, sphericalVertexDistance, cylindricalVertexDistance, FogEnvironmentalStart, FogEnvironmentalEnd, FogRenderDistanceStart, FogRenderDistanceEnd, fogColor);
}

layout(location = 6) flat in ivec2 chromaMaterialPhase;

layout(location = 5) in vec3 chromaMaterialEye;

void main() {
    ChromaMaterial chromaMaterial = chromaSampleTerrainMaterial(Sampler0, texCoord0, (UseRgss == 1 ? sampleRGSS(Sampler0, texCoord0, 1.0f / TextureSize) : sampleNearest(Sampler0, texCoord0, 1.0f / TextureSize)), chromaMaterialPhase, UseRgss == 1);
    vec4 color = chromaMaterial.color * vertexColor;
    #ifndef OIT_ALPHA_ONLY
    color = mix(FogColor * vec4(1, 1, 1, color.a), color, chunkVisibility);
    #endif
    #ifdef ALPHA_CUTOUT
    if (color.a < ALPHA_CUTOUT) {
        discard;
    }
    #endif

    #ifdef OIT_ALPHA_ONLY
    executeAlphaOnlyPhase(gl_FragCoord.z, color.a);
    #else
    fragColor = calculateFinalColor(color);

    #if !defined(OIT)
    // Only solid/cutout pipelines have spare framebuffer alpha for normals.
    // Native translucent terrain/block passes use ALPHA_CUTOUT=0.1 even
    // without OIT; their alpha must retain the material's real coverage.
    #ifdef ALPHA_CUTOUT
    if (ALPHA_CUTOUT >= 0.5)
    #endif
    if (ProjMat[2][3] != 0.0)
        fragColor.a = chromaMaterial.mapped ? chromaMaterialAlpha(chromaMaterial,
            chromaMaterialEye, texCoord0, transpose(mat3(ModelViewMat))) : 1.0;
    #endif
    #endif
}
