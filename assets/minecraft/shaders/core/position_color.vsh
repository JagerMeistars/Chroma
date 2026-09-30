#version 330
#extension GL_ARB_separate_shader_objects : require

#include <minecraft:dynamictransforms.glsl>
#include <minecraft:projection.glsl>

layout(location = 0) in vec3 Position;
layout(location = 1) in vec4 Color;

layout(location = 0) out vec4 vertexColor;

void main() {
    gl_Position = ProjMat * ModelViewMat * vec4(Position, 1.0);

    vertexColor = Color;

    // Known Axiom 6.1.2 CENTER_BOX mesh: local corners at +/-0.3 and uniform
    // scale >= 0.1, opaque grayscale vertex colors (tint is ColorModulator).
    // Its 50 ms position interpolation can differ from the scale's
    // target distance, so do not compare scale with camera distance. This covers
    // this editor mesh only; upstream mesh changes need a new signature.
    if (ProjMat[2][3] != 0.0 &&
        Color.a > 0.999999 &&
        all(lessThan(abs(Color.rgb - vec3(Color.r)), vec3(0.000001))) &&
        all(lessThan(abs(abs(Position) - vec3(0.3)), vec3(0.000001)))) {
        vec3 columnScale = vec3(length(ModelViewMat[0].xyz),
                                length(ModelViewMat[1].xyz),
                                length(ModelViewMat[2].xyz));
        if (columnScale.x >= 0.1 - 0.000001 &&
            all(lessThan(abs(columnScale - vec3(columnScale.x)),
                         vec3(max(0.000001, columnScale.x * 0.0001)))))
            gl_Position.z = gl_Position.w; // Existing non-world/HUD depth sentinel.
    }
}
