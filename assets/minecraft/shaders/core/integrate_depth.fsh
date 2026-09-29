#version 330
#extension GL_ARB_separate_shader_objects : require

uniform sampler2D InSampler;

layout(location = 0) in vec2 texCoord;

void main() {
    float depth = texelFetch(InSampler, ivec2(gl_FragCoord.xy), 0).r;

    if (depth == 0.0) {
        discard;
    }

    // Minecraft 26.3 integrates the separate hand/3D-HUD depth after all world
    // geometry and before end_of_frame. Mark only its actual covered pixels;
    // Chroma preserves their vanilla color and never learns them as world voxels.
    // GUI rendering clears depth afterwards. Empty HUD pixels keep world depth.
    gl_FragDepth = 1.0;
}
