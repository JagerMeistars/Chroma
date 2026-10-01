#version 450
#extension GL_ARB_separate_shader_objects : require
#include <chroma:shadow_config.glsl>

// Shadow-only fullscreen passes. A collapsed triangle runs no fragments.
void main() {
#if CHROMA_SHADOWS_ENABLED
    vec2 uv = vec2((gl_VertexIndex << 1) & 2, gl_VertexIndex & 2);
    gl_Position = vec4(uv * 2.0 - 1.0, 0.0, 1.0);
#else
    gl_Position = vec4(2.0, 2.0, 2.0, 1.0);
#endif
}
