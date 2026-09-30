#version 330
#extension GL_ARB_separate_shader_objects : require

#include <minecraft:globals.glsl>
#include <minecraft:projection.glsl>
#include <chroma:ferry_guard.glsl>
#include <minecraft:fog.glsl>
#include <minecraft:dynamictransforms.glsl>
#include <minecraft:oit.glsl>

uniform sampler2D Sampler0;

#ifdef DISSOLVE
uniform sampler2D DissolveMaskSampler;
#endif

#ifdef GLINT
uniform sampler2D GlintSampler;
#endif

layout(location = 0) in float sphericalVertexDistance;
layout(location = 1) in float cylindricalVertexDistance;
#ifdef PER_FACE_LIGHTING
layout(location = 2) in vec4 vertexPerFaceColorBack;
layout(location = 3) in vec4 vertexPerFaceColorFront;
#else
layout(location = 2) in vec4 vertexColor;
#endif

#ifndef EMISSIVE
layout(location = 4) in vec4 lightMapColor;
#endif

#ifndef NO_OVERLAY
layout(location = 5) in vec4 overlayColor;
#endif

layout(location = 6) in vec2 texCoord0;
#ifdef GLINT
layout(location = 7) in vec2 texCoordGlint;
#endif

#ifndef OIT_ALPHA_ONLY
layout(location = 0) out vec4 fragColor;
#endif

vec4 calculateFinalColor(vec4 color) {
    #ifndef NO_OVERLAY
    color.rgb = mix(overlayColor.rgb, color.rgb, overlayColor.a);
    #endif

    #ifndef EMISSIVE
    color *= lightMapColor;
    #endif

    #ifdef GLINT
    vec4 glintColor = GlintAlpha * texture(GlintSampler, texCoordGlint);
    // Matches BlendFuntion.GLINT
    color.rgb += glintColor.rgb * glintColor.rgb;
    #endif

    #ifdef OIT_ACCUMULATE
    color = sampleColorForAccumulation(color);
    vec4 fogColor = vec4(FogColor.rgb * color.a, FogColor.a);
    #else
    vec4 fogColor = FogColor;
    #endif

    return apply_fog(color, sphericalVertexDistance, cylindricalVertexDistance, FogEnvironmentalStart, FogEnvironmentalEnd, FogRenderDistanceStart, FogRenderDistanceEnd, fogColor);
}


// Chroma's marker data. Locations 0..7 belong to the vanilla shaders.
layout(location = 8) in float chromaMarker;
layout(location = 9) in vec2 chromaUV;
layout(location = 10) in vec4 chromaEye;
layout(location = 11) flat in vec4 chromaColor;
layout(location = 12) flat in int chromaShape;
layout(location = 13) flat in vec3 chromaFacing;
layout(location = 14) flat in int chromaSlot;

// Every marker writes the same current-camera header at the near plane.
// Scan the whole packet surface: draw order cannot select a source-address bound.
uint chromaHeaderWord(int word) {
    if (word == 0) return CHROMA_AUTO_HEADER;
    if (word <= 16) {
        int j = word - 1;
        return floatBitsToUint(ProjMat[j / 4][j % 4]);
    }
    if (word <= 25) {
        int j = word - 17;
        return floatBitsToUint(ModelViewMat[j / 3][j % 3]);
    }
    if (word == 26) return uint(chromaAutoCapacity(ivec2(ScreenSize)) - 1);
    return 0u;
}
vec4 chromaMarkerColor() {
    ivec2 size = ivec2(ScreenSize);
    ivec2 pixel = ivec2(gl_FragCoord.xy);
    if (chromaMarker > 1.5) {
        if (!chromaAutoHeaderPixel(pixel, size)) discard;
        int word = pixel.x;
        if (word == 27) {
            uint checksum = CHROMA_AUTO_CHECKSUM;
            for (int i = 0; i <= 26; ++i) checksum ^= chromaHeaderWord(i);
            return chromaAutoEncode(checksum);
        }
        return chromaAutoEncode(chromaHeaderWord(word));
    }
    // Derivatives restore the unchanged model geometry from its 4 by 2 raster.
    vec3 eye = chromaEye.xyz / chromaEye.w;
    vec3 dx = dFdx(eye) / dFdx(gl_FragCoord.x);
    vec3 dy = dFdy(eye) / dFdy(gl_FragCoord.y);
    vec2 uvDx = dFdx(chromaUV) / dFdx(gl_FragCoord.x);
    vec2 uvDy = dFdy(chromaUV) / dFdy(gl_FragCoord.y);
    bool uAlongX = abs(uvDx.x) > abs(uvDy.x);
    vec3 edgeU = uAlongX ? dx * 4.0 : dy * 2.0;
    vec3 edgeV = uAlongX ? dy * 2.0 : dx * 4.0;
    ivec2 origin = chromaAutoOrigin(chromaSlot, size);
    vec2 centrePixel = vec2(origin) + vec2(2.0, 1.0);
    vec3 centre = eye + dx * (centrePixel.x - gl_FragCoord.x)
                      + dy * (centrePixel.y - gl_FragCoord.y);
    ivec2 local = pixel - origin;
    if (chromaSlot < 0 || chromaSlot >= chromaAutoCapacity(size) ||
        local.x < 0 || local.x >= 4 || local.y < 0 || local.y >= 2) discard;
    uint words[8];
    words[0] = CHROMA_AUTO_SIGNATURE | uint(chromaShape);
    words[1] = floatBitsToUint(centre.x);
    words[2] = floatBitsToUint(centre.y);
    words[3] = floatBitsToUint(centre.z);
    words[4] = chromaAutoPackScales(length(edgeU), length(edgeV));
    words[5] = chromaAutoOctEncode(chromaFacing);
    words[6] = chromaAutoDecode(vec4(chromaColor.rgb, 1.0));
    words[7] = chromaAutoChecksum(words);
    return chromaAutoEncode(words[local.x + local.y * 4]);
}

void main() {

    if (chromaMarker > 0.5) {
        vec4 markerColor = chromaMarkerColor();
        #ifdef OIT_ALPHA_ONLY
        executeAlphaOnlyPhase(gl_FragCoord.z, markerColor.a);
        #elif defined(OIT_ACCUMULATE)
        fragColor = sampleColorForAccumulation(markerColor);
        #else
        fragColor = markerColor;
        #endif
        return;
    }
    // First-person items can clear scene depth before end_of_frame reads data.
    if (chromaReservedPixel()) discard;

    vec4 color = texture(Sampler0, texCoord0);

    #ifdef OIT_ADDITIVE
    color.a = min(0.99, color.a);
    #endif

    #ifdef ALPHA_CUTOUT
    if (color.a < ALPHA_CUTOUT) {
        discard;
    }
    #endif

    #ifdef PER_FACE_LIGHTING
    vec4 faceVertexColor = gl_FrontFacing ? vertexPerFaceColorFront : vertexPerFaceColorBack;
    #else
    vec4 faceVertexColor = vertexColor;
    #endif

    #ifdef DISSOLVE
    if (faceVertexColor.a < texture(DissolveMaskSampler, texCoord0).a) {
        discard;
    }
    // The dissolve effect entirely replaces translucency
    faceVertexColor.a = 1.0;
    #endif

    color *= faceVertexColor * ColorModulator;

    #ifdef GLINT
    color.a = max(color.a, GlintAlpha);
    #endif

    #ifdef OIT_ALPHA_ONLY
    executeAlphaOnlyPhase(gl_FragCoord.z, color.a);
    #else
    fragColor = calculateFinalColor(color);
    #endif
}
