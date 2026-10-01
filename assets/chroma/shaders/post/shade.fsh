#version 450
#extension GL_ARB_separate_shader_objects : require
#include <chroma:bits.glsl>

// Reconstruct visible surfaces from depth, add the marker lights, then apply
// depth fog. The matrix and colour caches supply lamp data.

// Light appearance. Marker scale.x controls radius; scale.y controls intensity.
#define RADIUS_GAIN     CHROMA_RADIUS_GAIN
#define INTENSITY_GAIN  70.0
#define ENABLE_ACES       1
#define TONE_SAT          0.6
#define LIGHT_STRENGTH    0.3

#define LOOK_CORE         4.0
#define LOOK_FULL_LUM     3.0
#define FALLOFF_CORE      0.15

// Medium spotlight angles. Narrow and wide variants are selected per marker.
#define SPOT_COS_INNER    0.95
#define SPOT_COS_OUTER    0.88
#define DOME_EDGE         0.25

// Optional extra fog affects the whole scene, even without lamps. Off by default.
#define FOG_COLOR    vec3(0.05, 0.06, 0.09)
#define FOG_DENSITY  0.0
#define FOG_MAX      0.85
#define FOG_SKY      0.5

#include <minecraft:globals.glsl>
#include <chroma:lighting.glsl>
#include <chroma:auto_read.glsl>
#include <chroma:shadow_filter.glsl>

uniform sampler2D InSampler;
uniform sampler2D InDepthSampler;
uniform sampler2D ColorSampler;
uniform sampler2D MatDecSampler;
uniform sampler2D TileSampler;
uniform sampler2D CatalogSampler;

float chromaDepth(vec2 uv) {
    return texture(InDepthSampler, uv).r;
}

layout(location = 0) in vec2 texCoord;
layout(location = 1) flat in int cameraValid;
layout(location = 2) flat in mat4 cameraInvProj;
layout(location = 6) flat in mat4 cameraProj;
layout(location = 10) flat in vec3 cameraDown;
layout(location = 11) flat in int autoLastAddress;
layout(location = 12) flat in mat3 cameraInvRot;
layout(location = 0) out vec4 fragColor;

vec3 aces(vec3 x) {
    return clamp((x * (2.51 * x + 0.03)) / (x * (2.43 * x + 0.59) + 0.14), 0.0, 1.0);
}

vec3 reconstructEyePosAt(vec2 uv, float d, mat4 invProj) {
    // Minecraft 26.3 uses reversed depth with zero-to-one clip coordinates.
    float ndcZ = d;
    vec4 clip = vec4(uv * 2.0 - 1.0, ndcZ, 1.0);
    vec4 eye  = invProj * clip;
    return eye.xyz / eye.w;
}

#include <chroma:entity_shadow.glsl>

// Camera matrices are decoded once per screen-triangle vertex. Each shaded
// pixel visits only the sources in its tile.
void main() {
    vec3 albedo = texture(InSampler, texCoord).rgb;
    vec2 suv = texCoord;
    ivec2 ipx = ivec2(gl_FragCoord.xy);
    ivec2 frameSize = textureSize(InSampler, 0);
    int cleanY = -1;
    if (chromaAutoHeaderPixel(ipx, frameSize)) cleanY = frameSize.y - 2;
    else {
        int address = chromaRawAddressAtPixel(ipx, frameSize);
        if (address >= 0 && address <= autoLastAddress && chromaCatalogHas(CatalogSampler, address))
            cleanY = chromaAutoOrigin(address, frameSize).y - 1;
    }
    if (cleanY >= 0) {
        albedo = texelFetch(InSampler, ivec2(ipx.x, cleanY), 0).rgb;
        suv.y = (float(cleanY) + 0.5) / float(frameSize.y);
    }
    float d = chromaDepth(suv);
#if !CHROMA_STATIC_WORLD && CHROMA_PARTICLE_DEPTH_MASK
    // Opaque particles keep their native colour/depth test and carry alpha=0
    // as an observed-geometry exclusion tag. OIT particles use the depth tag.
    if (d > 0.000001 && texelFetch(InSampler, ivec2(suv * vec2(frameSize)), 0).a < 0.5 / 255.0) {
        fragColor = vec4(albedo, 1.0);
        return;
    }
#endif
    // The hand/3D-HUD integration hook marks only covered pixels. Preserve their
    // vanilla color instead of interpreting their different projection as world.
    if (d >= 0.999999) {
        fragColor = vec4(albedo, 1.0);
        return;
    }
    bool isSky = d <= 0.000001;
    float fogDist = isSky ? 1.0e4 : 0.05 / max(d, 1.0e-7);
    float fogF = (1.0 - exp(-fogDist * FOG_DENSITY)) * (isSky ? FOG_SKY : 1.0);
    fogF = min(fogF, FOG_MAX);
    if (isSky) {
        float skyLum = dot(albedo, vec3(0.2125, 0.7154, 0.0721));
        fogF *= 1.0 - smoothstep(0.08, 0.25, skyLum);
    }
    if (cameraValid == 0) {
        fragColor = vec4(mix(albedo, FOG_COLOR, fogF), 1.0);
        return;
    }
    ivec2 tileSize = textureSize(TileSampler, 0);
    tileSize.x /= 4;
    ivec2 tilePixel = clamp(ivec2(suv * vec2(tileSize)), ivec2(0), tileSize - 1);
    uvec4 maskBytes0 = uvec4(texelFetch(TileSampler, ivec2(tilePixel.x * 4, tilePixel.y), 0) * 255.0 + 0.5);
    uvec4 maskBytes1 = uvec4(texelFetch(TileSampler, ivec2(tilePixel.x * 4 + 1, tilePixel.y), 0) * 255.0 + 0.5);
    uvec4 maskBytes2 = uvec4(texelFetch(TileSampler, ivec2(tilePixel.x * 4 + 2, tilePixel.y), 0) * 255.0 + 0.5);
    uvec4 maskBytes3 = uvec4(texelFetch(TileSampler, ivec2(tilePixel.x * 4 + 3, tilePixel.y), 0) * 255.0 + 0.5);
    uint mask0 = maskBytes0.r | (maskBytes0.g << 8) | (maskBytes0.b << 16) | (maskBytes0.a << 24);
    uint mask1 = maskBytes1.r | (maskBytes1.g << 8) | (maskBytes1.b << 16) | (maskBytes1.a << 24);
    uint mask2 = maskBytes2.r | (maskBytes2.g << 8) | (maskBytes2.b << 16) | (maskBytes2.a << 24);
    uint mask3 = maskBytes3.r | (maskBytes3.g << 8) | (maskBytes3.b << 16) | (maskBytes3.a << 24);
    if ((mask0 | mask1 | mask2 | mask3) == 0u) {
        fragColor = vec4(mix(albedo, FOG_COLOR, fogF), 1.0);
        return;
    }

    vec3 fragPos = vec3(0.0);
    vec3 normal = vec3(0.0);
    if (!isSky) {
        fragPos = reconstructEyePosAt(suv, d, cameraInvProj);
        vec2 tpx = 1.0 / vec2(textureSize(InDepthSampler, 0));
        float dLn = chromaDepth(suv - vec2(tpx.x, 0.0));
        float dRn = chromaDepth(suv + vec2(tpx.x, 0.0));
        float dDn = chromaDepth(suv - vec2(0.0, tpx.y));
        float dUn = chromaDepth(suv + vec2(0.0, tpx.y));
        vec3 pL = reconstructEyePosAt(suv - vec2(tpx.x, 0.0), dLn, cameraInvProj);
        vec3 pR = reconstructEyePosAt(suv + vec2(tpx.x, 0.0), dRn, cameraInvProj);
        vec3 pD = reconstructEyePosAt(suv - vec2(0.0, tpx.y), dDn, cameraInvProj);
        vec3 pU = reconstructEyePosAt(suv + vec2(0.0, tpx.y), dUn, cameraInvProj);
        vec3 dxp = (abs(dRn - d) < abs(d - dLn)) ? (pR - fragPos) : (fragPos - pL);
        vec3 dyp = (abs(dUn - d) < abs(d - dDn)) ? (pU - fragPos) : (fragPos - pD);
        normal = normalize(cross(dxp, dyp));
        if (dot(normal, fragPos) > 0.0) normal = -normal;
    }
    vec3 radiance = vec3(0.0);
    float reachLum = 0.0;
    float shadowDebug = 1.0;
    vec3 worldReceiver = cameraInvRot * fragPos;
    vec3 worldNormal = cameraInvRot * normal;
    worldReceiver = chromaShadowReceiver(worldReceiver, worldNormal);
    vec3 lightReceiver = fragPos;
#if CHROMA_SHADOW_PIXELATE
    // Falloff, cone edges and shadows use the same world-grid surface sample.
    lightReceiver = transpose(cameraInvRot) * worldReceiver;
#endif
#if CHROMA_SHADOWS_ENABLED && !CHROMA_STATIC_WORLD && CHROMA_ENTITY_SHADOWS == 2 && CHROMA_TRANSPARENT_DEPTH_MASK
    // Keep receiving normal Chroma/world shadows, without contact self-shadow.
    bool entityReceiver = chromaEntityShadowTag(texelFetch(InSampler,
        ivec2(suv * vec2(frameSize)), 0).a);
#endif
    vec4 previousShadowSource = vec4(0.0);
    float previousVisibility = 1.0;
    while ((mask0 | mask1 | mask2 | mask3) != 0u) {
        int bank = mask0 != 0u ? 0 : (mask1 != 0u ? 1 : (mask2 != 0u ? 2 : 3));
        uint activeMask = bank == 0 ? mask0 : (bank == 1 ? mask1 : (bank == 2 ? mask2 : mask3));
        int k = chromaFirstBit(activeMask) + bank * 32;
        if (bank == 0) mask0 &= mask0 - 1u;
        else if (bank == 1) mask1 &= mask1 - 1u;
        else if (bank == 2) mask2 &= mask2 - 1u;
        else mask3 &= mask3 - 1u;
        vec3 lPos = chromaMdLampEyeOf(MatDecSampler, k);
        float lRad = max(chromaMdLampRadiusOf(MatDecSampler, k) * RADIUS_GAIN, 0.001);
        int lShape = chromaMdLampShapeOf(MatDecSampler, k);
        float surfaceWeight = 0.0;
        float unshadowedWeight = 0.0;
        float visibility = 1.0;
        if (!isSky) {
            vec3 toL = lPos - lightReceiver;
            float dist = length(toL);
            if (dist <= lRad) {
                vec3 L = toL / max(dist, 1e-4);
                float diff = max(dot(normal, L), 0.0);
                float rx = clamp(dist / lRad, 0.0, 1.0);
                float fall = 1.0 - smoothstep(FALLOFF_CORE, 1.0, rx);
                if (lShape >= 1 && lShape <= 3) {
                    float cosIn = SPOT_COS_INNER, cosOut = SPOT_COS_OUTER;
                    if (lShape == 1) { cosIn = 0.985; cosOut = 0.96; }
                    else if (lShape == 3) { cosIn = 0.88; cosOut = 0.74; }
                    vec3 axis = -normalize(chromaMdLampFacingOf(MatDecSampler, k));
                    fall *= smoothstep(cosOut, cosIn, dot(-L, axis));
                } else if (lShape == 4) {
                    fall *= smoothstep(0.0, DOME_EDGE, dot(normalize(-toL), cameraDown));
                }
                surfaceWeight = LIGHT_STRENGTH * diff * fall;
                unshadowedWeight = surfaceWeight;
#if CHROMA_SHADOWS_ENABLED
                if (surfaceWeight > 0.0001) {
                    // Colour and cone shape do not change radial occlusion.
                    // Reuse an exact colocated source; distinct positions stay independent.
                    vec4 shadowSource = vec4(lPos, lRad);
                    if (any(notEqual(shadowSource, previousShadowSource))) {
                        previousVisibility = chromaShadow(k, worldReceiver,
                            worldNormal, cameraInvRot * lPos, lRad);
#if !CHROMA_STATIC_WORLD && CHROMA_ENTITY_SHADOWS == 2 && CHROMA_TRANSPARENT_DEPTH_MASK
                        if (previousVisibility > 0.0 && !entityReceiver)
                            previousVisibility *= chromaEntityShadow(lightReceiver, normal, lPos, frameSize);
#endif
                        previousShadowSource = shadowSource;
                    }
                    visibility = previousVisibility;
                    surfaceWeight *= visibility;
                    shadowDebug = min(shadowDebug, visibility);
                }
#endif
            }
        }
        if (surfaceWeight == 0.0) continue;
        float lInt = max(chromaMdRenderIntensity(MatDecSampler, k) * INTENSITY_GAIN, 0.0);
        vec3 lCol = texelFetch(ColorSampler, ivec2(k, 0), 0).rgb;
        radiance += lCol * (lInt * surfaceWeight);
        // Saturate each lamp's response before applying shadow coverage. A
        // bright lamp's first visible sample must not fill the whole penumbra.
        // RGB still uses actual shadowed energy; fully lit output is unchanged,
        // and a blocked lamp contributes nothing to another lamp's response.
        float unshadowedLum = dot(lCol, vec3(0.2125, 0.7154, 0.0721)) * lInt * unshadowedWeight;
        reachLum += min(unshadowedLum, LOOK_FULL_LUM) * visibility;
    }

    float radLum = dot(radiance, vec3(0.2125, 0.7154, 0.0721));
    vec3 outc = albedo;
    float reach = 0.0;
    if (radLum > 1e-4) {
        vec3 hueDir = radiance / radLum;
        float env = smoothstep(0.0, LOOK_FULL_LUM, reachLum);
        outc = albedo * (1.0 + hueDir * LOOK_CORE);
#if ENABLE_ACES
        vec3 perCh = aces(outc);
        float lumIn = dot(outc, vec3(0.2125, 0.7154, 0.0721));
        float lumOut = aces(vec3(lumIn)).r;
        vec3 hue = outc * (lumOut / max(lumIn, 1e-4));
        outc = mix(perCh, hue, TONE_SAT);
#endif
        reach = env;
    }
    outc = mix(albedo, outc, reach);
    outc = mix(outc, FOG_COLOR, fogF);
    fragColor = vec4(outc, 1.0);
#if CHROMA_SHADOWS_ENABLED && CHROMA_SHADOW_DEBUG
    fragColor = vec4(vec3(shadowDebug), 1.0);
#endif
}
