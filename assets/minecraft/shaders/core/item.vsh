#version 330
#extension GL_ARB_separate_shader_objects : require

#include <minecraft:light.glsl>
#include <minecraft:fog.glsl>
#include <minecraft:dynamictransforms.glsl>
#include <minecraft:projection.glsl>
#include <minecraft:globals.glsl>
#include <chroma:auto_transport.glsl>
#include <minecraft:sample_lightmap.glsl>

layout(location = 0) in vec3 Position;
layout(location = 1) in vec4 Color;
layout(location = 2) in vec2 UV0;
layout(location = 3) in ivec2 UV1;
layout(location = 4) in ivec2 UV2;
#ifdef GLINT_SPECIAL
layout(location = 5) in vec2 UV3;
#endif
layout(location = 6) in vec3 Normal;

#ifndef OIT_ALPHA_ONLY
uniform sampler2D Sampler1;
uniform sampler2D Sampler2;

layout(location = 0) out float sphericalVertexDistance;
layout(location = 1) out float cylindricalVertexDistance;
#endif
layout(location = 2) out vec4 vertexColor;
#ifndef OIT_ALPHA_ONLY
layout(location = 3) out vec4 lightMapColor;
layout(location = 4) out vec4 overlayColor;
#endif

layout(location = 5) out vec2 texCoord0;
#ifdef GLINT
layout(location = 6) out vec2 texCoordGlint;
#endif

uniform sampler2D Sampler0;

// Chroma's marker data. Locations 0..7 belong to the vanilla shaders.
layout(location = 8) out float chromaMarker;
layout(location = 9) out vec2 chromaUV;
layout(location = 10) out vec4 chromaEye;
layout(location = 11) flat out vec4 chromaColor;
layout(location = 12) flat out int chromaShape;
layout(location = 13) flat out vec3 chromaFacing;
layout(location = 14) flat out int chromaSlot;

// R/G identify Chroma. B carries shape, local corner, and header/payload kind.
bool chromaMatchKey(vec2 uv, vec2 tx) {
    vec2 tolerance = vec2(3.0 / 255.0);
    vec2 key = vec2(76.0, 195.0) / 255.0;
    return all(lessThan(abs(textureLod(Sampler0, uv, 0.0).rg - key), tolerance)) &&
           all(lessThan(abs(textureLod(Sampler0, uv + vec2(tx.x, 0.0), 0.0).rg - key), tolerance)) &&
           all(lessThan(abs(textureLod(Sampler0, uv - vec2(tx.x, 0.0), 0.0).rg - key), tolerance)) &&
           all(lessThan(abs(textureLod(Sampler0, uv + vec2(0.0, tx.y), 0.0).rg - key), tolerance)) &&
           all(lessThan(abs(textureLod(Sampler0, uv - vec2(0.0, tx.y), 0.0).rg - key), tolerance));
}

void main() {
    gl_Position = ProjMat * ModelViewMat * vec4(Position, 1.0);

    #ifndef OIT_ALPHA_ONLY
    sphericalVertexDistance = fog_spherical_distance(Position);
    cylindricalVertexDistance = fog_cylindrical_distance(Position);
    #endif
    vertexColor = minecraft_mix_light(Light0_Direction, Light1_Direction, Normal, Color);
    #ifndef OIT_ALPHA_ONLY
    lightMapColor = sample_lightmap(Sampler2, UV2);
    overlayColor = texelFetch(Sampler1, UV1, 0);
    #endif

    texCoord0 = UV0;
    #ifdef GLINT
    #ifdef GLINT_SPECIAL
    texCoordGlint = (TextureMat * vec4(UV3, 0.0, 1.0)).xy;
    #else
    texCoordGlint = (TextureMat * vec4(UV0, 0.0, 1.0)).xy;
    #endif
    #endif

    // Frame-local vertex addresses replace hand-assigned source slots.
    chromaMarker = 0.0;
    chromaUV = UV0;
    chromaEye = vec4(0.0, 0.0, 0.0, 1.0);
    chromaColor = vec4(Color.rgb, 1.0);
    chromaShape = 0;
    chromaFacing = vec3(0.0, 0.0, -1.0);
    chromaSlot = 0;
    vec2 chromaTexel = 1.0 / vec2(textureSize(Sampler0, 0));
    if (chromaMatchKey(UV0, chromaTexel)) {
        int variant = int(textureLod(Sampler0, UV0, 0.0).b * 255.0 + 0.5);
        int corner = (variant >> 3) & 3;
        bool header = (variant & 32) != 0;
        int quadFirst = gl_VertexIndex - corner;
        chromaSlot = quadFirst / 4 + (header ? 1 : 0);
        chromaMarker = header ? 2.0 : 1.0;
        chromaShape = variant & 7;
        chromaFacing = normalize((ModelViewMat * vec4(Normal, 0.0)).xyz);
        chromaEye = vec4((ModelViewMat * vec4(Position, 1.0)).xyz, 1.0);
        ivec2 size = ivec2(ScreenSize);
        ivec2 origin = header ? ivec2(0, size.y - 1) : chromaAutoOrigin(chromaSlot, size);
        vec2 extent = header ? vec2(32.0, 1.0) : vec2(4.0, 2.0);
        vec2 pixel = vec2(origin);
        if (corner == 0) pixel += vec2(0.0, extent.y);
        if (corner == 2) pixel += vec2(extent.x, 0.0);
        if (corner == 3) pixel += extent;
        // Reverse-depth near plane: terrain must not hide the camera packet.
        // Every header writer carries identical camera data and scan bounds.
        gl_Position = vec4(pixel / ScreenSize * 2.0 - 1.0, 1.0, 1.0);
        if (!header && (chromaSlot < 0 || chromaSlot >= chromaAutoCapacity(size)))
            gl_Position = vec4(2.0, 2.0, 1.0, 1.0);
    }
}
