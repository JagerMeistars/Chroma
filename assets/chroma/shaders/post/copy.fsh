#version 450
#extension GL_ARB_separate_shader_objects : require

// Exact integer-coordinate copy for packed RGBA8 cache data and the final frame.
// texelFetch preserves every byte without interpolation.

uniform sampler2D InSampler;

layout(location = 0) out vec4 fragColor;

void main() {
    fragColor = texelFetch(InSampler, ivec2(gl_FragCoord.xy), 0);
}
