#version 330
#extension GL_ARB_separate_shader_objects : require

// Can't moj_import in things used during startup, when resource packs don't exist.
// This is a copy of dynamicimports.glsl and projection.glsl
layout(std140) uniform DynamicTransforms {
    mat4 ModelViewMat;
    mat4 TextureMat;
    vec4 ColorModulator;
    vec3 ModelOffset;
};
layout(std140) uniform Projection {
    mat4 ProjMat;
};

layout(location = 0) in vec3 Position;
layout(location = 1) in vec2 UV0;
layout(location = 2) in vec4 Color;

layout(location = 0) out vec2 texCoord0;
layout(location = 1) out vec4 vertexColor;

layout(location = 2) flat out ivec2 chromaMaterialPhase;
uniform sampler2D Sampler0;

void main() {
    gl_Position = ProjMat * ModelViewMat * vec4(Position, 1.0);
    // Atlas mip 0/1 padding can shift the sprite off the 4x4 grid.
    // Native pixel-aligned model UVs retain that phase at every vertex.
    chromaMaterialPhase = textureSize(Sampler0, 2).x > 0 ? ivec2(0) :
        (ivec2(round(UV0 * vec2(textureSize(Sampler0, 0)))) & ivec2(3));

    texCoord0 = UV0;
    vertexColor = Color;
}
