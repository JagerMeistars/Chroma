#version 330
#extension GL_ARB_separate_shader_objects : require

#include <minecraft:fog.glsl>
#include <minecraft:dynamictransforms.glsl>
#include <minecraft:oit.glsl>
#include <chroma:shadow_config.glsl>

uniform sampler2D Sampler0;

layout(location = 0) in float sphericalVertexDistance;
layout(location = 1) in float cylindricalVertexDistance;
layout(location = 2) in vec2 texCoord0;
layout(location = 3) in vec4 vertexColor;

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
    vec4 color = texture(Sampler0, texCoord0) * vertexColor * ColorModulator;
    if (color.a < 0.1) {
        discard;
    }
    #ifdef OIT_ALPHA_ONLY
    executeAlphaOnlyPhase(gl_FragCoord.z, color.a);
    #if !CHROMA_STATIC_WORLD && CHROMA_PARTICLE_DEPTH_MASK && defined(OIT_DEPTH_BOUNDS)
    // Only the final OIT composite consumes this device-depth channel. Keep
    // linear range, opaque cutoff, visibility tests and color accumulation native.
    // Covered particle pixels become unknown to Dynamic after world rendering.
    fragColor.b = 1.0;
    #endif
    #else
    fragColor = calculateFinalColor(color);
    #if !CHROMA_STATIC_WORLD && CHROMA_PARTICLE_DEPTH_MASK && !defined(OIT)
    // With Improved Transparency ON, this is the unblended opaque particle
    // pass: alpha is metadata, while native RGB and depth stay untouched.
    // Classic translucent particles share this shader, so disable the setting
    // before turning Improved Transparency OFF; their alpha controls blending.
    fragColor.a = 0.0;
    #endif
    #endif
}
