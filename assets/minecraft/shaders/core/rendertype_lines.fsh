#version 330
#extension GL_ARB_separate_shader_objects : require

#include <minecraft:fog.glsl>
#include <minecraft:dynamictransforms.glsl>
#include <minecraft:oit.glsl>
#include <minecraft:globals.glsl>
#include <minecraft:projection.glsl>
#include <chroma:auto_read.glsl>

layout(location = 0) in float sphericalVertexDistance;
layout(location = 1) in float cylindricalVertexDistance;
layout(location = 2) in vec4 vertexColor;

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

void main() {
    // Matched editor handles use depth 1, but Axiom's ALWAYS_PASS draw can
    // still overwrite Chroma's colour packets. Reserve transport pixels for
    // this overlay without changing the shared debug_point varying interface.
    if (gl_FragCoord.z == 1.0 && ProjMat[2][3] != 0.0) {
        ivec2 pixel = ivec2(gl_FragCoord.xy);
        ivec2 size = ivec2(ScreenSize);
        if (chromaAutoHeaderPixel(pixel, size) ||
            chromaRawAddressAtPixel(pixel, size) >= 0) discard;
    }

    vec4 color = vertexColor * ColorModulator;
    #ifdef OIT_ALPHA_ONLY
    executeAlphaOnlyPhase(gl_FragCoord.z, color.a);
    #else
    fragColor = calculateFinalColor(color);
    #endif
}
