#version 450
#extension GL_ARB_separate_shader_objects : require
#include <minecraft:globals.glsl>
#include <chroma:lighting.glsl>
#include <chroma:voxel_space.glsl>
uniform sampler2D MatDecSampler;
uniform sampler2D MetaSampler;
layout(location = 0) flat out int cameraValid;
layout(location = 1) flat out mat4 cameraProj;
layout(location = 5) flat out mat4 cameraInvProj;
layout(location = 9) flat out mat3 cameraRot;
layout(location = 12) flat out int historyValid;
layout(location = 13) flat out ivec3 previousOrigin;
layout(location = 14) flat out uint frame;
void main() {
    vec2 uv = vec2((gl_VertexIndex << 1) & 2, gl_VertexIndex & 2);
    gl_Position = vec4(uv * 2.0 - 1.0, 0.0, 1.0);
    // One fragment now owns one cell. Decode draw-constant state only at the
    // fullscreen triangle's vertices, rather than sixteen million times.
    cameraValid = chromaMdValid(MatDecSampler, 0) ? 1 : 0;
    cameraProj = mat4(0.0);
    cameraInvProj = mat4(0.0);
    cameraRot = mat3(1.0);
    if (cameraValid != 0) {
        for (int i = 0; i < 16; ++i)
            cameraProj[i / 4][i % 4] = chromaMdFloat(MatDecSampler, 1 + i);
        cameraInvProj = chromaMdInvProj(MatDecSampler, 0);
        cameraRot = chromaMdRot(MatDecSampler, 0);
    }
    historyValid = chromaVoxDecode(texelFetch(MetaSampler, ivec2(0,0), 0)) == CHROMA_VOX_META_MAGIC ? 1 : 0;
    for (int i = 0; i < 3; ++i)
        previousOrigin[i] = int(chromaVoxDecode(texelFetch(MetaSampler, ivec2(i+1,0), 0)));
    frame = chromaVoxDecode(texelFetch(MetaSampler, ivec2(4,0), 0));
}
