#version 450
#extension GL_ARB_separate_shader_objects : require
#include <chroma:auto_read.glsl>
#include <chroma:lighting.glsl>
#include <chroma:flicker.glsl>
#include <minecraft:globals.glsl>
uniform sampler2D MainSampler;
uniform sampler2D IndicesSampler;
uniform sampler2D CountsSampler;
layout(location = 0) out vec4 fragColor;
void main() {
    int t = int(gl_FragCoord.x);
    uint value = 0u;
    if (t >= MATDEC_LAMP(0)) {
        int k = (t - MATDEC_LAMP(0)) / 16;
        int field = (t - MATDEC_LAMP(0)) % 16;
        uint encoded = chromaAutoDecode(texelFetch(IndicesSampler, ivec2(k, 0), 0));
        if (encoded == 0u) { fragColor = chromaAutoEncode(0u); return; }
        int address = int(encoded - 1u);
        if (field == 0 || field == 10) value = 1u;
        else if (field <= 3) value = chromaRawWord(MainSampler, address, field);
        else if (field <= 5) value = floatBitsToUint(chromaAutoUnpackScales(chromaRawWord(MainSampler, address, 4))[field - 4]);
        else if (field == 6) value = chromaRawWord(MainSampler, address, 0) & 7u;
        else if (field <= 9) value = floatBitsToUint(chromaAutoOctDecode(chromaRawWord(MainSampler, address, 5))[field - 7]);
        else if (field == 11) value = uint(address);
        else if (field == 12) {
            float intensity = chromaAutoUnpackScales(chromaRawWord(MainSampler, address, 4)).y;
            int shape = int(chromaRawWord(MainSampler, address, 0) & 7u);
            vec3 colour = chromaAutoEncode(chromaRawWord(MainSampler, address, 6)).rgb;
            value = floatBitsToUint(intensity * chromaSourceFlicker(shape, colour, GameTime * 24000.0));
        }
    } else if (t == 42) {
        for (int i = 0; i < 64; ++i) value += chromaAutoDecode(texelFetch(CountsSampler, ivec2(i, 0), 0));
    } else if (t == 43) {
        value = chromaHeaderValid(MainSampler) ? chromaHeaderWord(MainSampler, 26) : 0u;
    } else if (t < 42 && chromaHeaderValid(MainSampler)) {
        if (t == 0) value = 1u;
        else if (t <= 16) value = chromaHeaderWord(MainSampler, t);
        else if (t <= 32) {
            mat4 projection;
            for (int i = 0; i < 16; ++i) projection[i / 4][i % 4] = uintBitsToFloat(chromaHeaderWord(MainSampler, i + 1));
            mat4 invProjection = inverse(projection);
            int j = t - 17;
            value = floatBitsToUint(invProjection[j / 4][j % 4]);
        } else value = chromaHeaderWord(MainSampler, t - 16);
    }
    fragColor = chromaAutoEncode(value);
}
