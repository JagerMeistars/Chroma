#version 330
#extension GL_ARB_separate_shader_objects : require

#include <minecraft:globals.glsl>
#include <minecraft:projection.glsl>
#include <chroma:auto_read.glsl>

// Can't moj_import in things used during startup, when resource packs don't exist.
// This is a copy of dynamicimports.glsl
layout(std140) uniform DynamicTransforms {
    mat4 ModelViewMat;
    mat4 TextureMat;
    vec4 ColorModulator;
    vec3 ModelOffset;
};

uniform sampler2D Sampler0;

layout(location = 0) in vec2 texCoord0;
layout(location = 1) in vec4 vertexColor;

layout(location = 0) out vec4 fragColor;

void main() {
    // Vanilla block/water/fire screen effects use this shared shader after
    // world rendering. Preserve Chroma's packets only in their 3D-HUD pass;
    // ordinary orthographic GUI/startup draws keep the complete native image.
    // Reserving possible payload cells leaves gaps in a fullscreen overlay.
    if (ProjMat[2][3] != 0.0) {
        ivec2 pixel = ivec2(gl_FragCoord.xy);
        ivec2 size = ivec2(ScreenSize);
        if (chromaAutoHeaderPixel(pixel, size) ||
            chromaRawAddressAtPixel(pixel, size) >= 0) discard;
    }

    vec4 color = texture(Sampler0, texCoord0) * vertexColor;
    if (color.a == 0.0) {
        discard;
    }
    fragColor = color * ColorModulator;
}
