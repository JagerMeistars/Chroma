#version 450
#extension GL_ARB_separate_shader_objects : require
#include <minecraft:globals.glsl>
#include <chroma:voxel_space.glsl>
uniform sampler2D InSampler;
layout(location = 0) flat in int cameraValid;
layout(location = 12) flat in int historyValid;
layout(location = 13) flat in ivec3 previousOrigin;
layout(location = 14) flat in uint frame;
layout(location = 0) out vec4 fragColor;
void main() {
    if (cameraValid == 0) discard;
    ivec2 p = ivec2(gl_FragCoord.xy);
    int index = (p.x + 4096 * p.y) >> 2;
    ivec3 wrapped = ivec3(index % CHROMA_VOX_N,
        (index / CHROMA_VOX_N) % CHROMA_VOX_N, index / (CHROMA_VOX_N * CHROMA_VOX_N));
    ivec3 origin = chromaVoxOrigin();
    ivec3 voxel = origin + ((wrapped - origin) & (CHROMA_VOX_N - 1));
    bool retained = historyValid != 0 && chromaVoxContains(voxel, previousOrigin);
    if (retained && !chromaVoxUpdateSlice(voxel, frame)) discard;
    fragColor = texelFetch(InSampler, p, 0);
}
