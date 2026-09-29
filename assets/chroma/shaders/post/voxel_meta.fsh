#version 450
#extension GL_ARB_separate_shader_objects : require
#include <minecraft:globals.glsl>
#include <chroma:lighting.glsl>
#include <chroma:voxel_space.glsl>
uniform sampler2D MetaSampler;
uniform sampler2D MatDecSampler;
layout(location = 0) out vec4 fragColor;
void main() {
    uint value = 0u;
    int field = int(gl_FragCoord.x);
    if (!chromaMdValid(MatDecSampler, 0)) {
        fragColor = texelFetch(MetaSampler, ivec2(field, 0), 0);
        return;
    }
    if (chromaMdValid(MatDecSampler, 0)) {
        if (field == 0) value = CHROMA_VOX_META_MAGIC;
        else if (field <= 3) value = uint(chromaVoxOrigin()[field - 1]);
        else if (field == 4) {
            bool valid = chromaVoxDecode(texelFetch(MetaSampler, ivec2(0, 0), 0)) == CHROMA_VOX_META_MAGIC;
            value = valid ? chromaVoxDecode(texelFetch(MetaSampler, ivec2(4, 0), 0)) + 1u : 0u;
        }
    }
    fragColor = chromaVoxEncode(value);
}
