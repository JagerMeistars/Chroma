#version 330
#extension GL_ARB_separate_shader_objects : require

#include <minecraft:fog.glsl>
#include <minecraft:dynamictransforms.glsl>
#include <minecraft:projection.glsl>
#include <minecraft:sample_lightmap.glsl>

layout(location = 0) in vec3 Position;
layout(location = 1) in vec2 UV0;
layout(location = 2) in vec4 Color;
layout(location = 3) in ivec2 UV2;

uniform sampler2D Sampler2;

layout(location = 0) out float sphericalVertexDistance;
layout(location = 1) out float cylindricalVertexDistance;
layout(location = 2) out vec2 texCoord0;
layout(location = 3) out vec4 vertexColor;

layout(location = 4) flat out ivec2 chromaMaterialPhase;
uniform sampler2D Sampler0;

void main() {
    gl_Position = ProjMat * ModelViewMat * vec4(Position, 1.0);
    // Atlas mip 0/1 padding can shift the sprite off the 4x4 grid.
    // Native pixel-aligned model UVs retain that phase at every vertex.
    chromaMaterialPhase = textureSize(Sampler0, 2).x > 0 ? ivec2(0) :
        (ivec2(round(UV0 * vec2(textureSize(Sampler0, 0)))) & ivec2(3));

    sphericalVertexDistance = fog_spherical_distance(Position);
    cylindricalVertexDistance = fog_cylindrical_distance(Position);
    texCoord0 = UV0;
    vertexColor = Color * sample_lightmap(Sampler2, UV2);
}
