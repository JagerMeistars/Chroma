#version 450
#extension GL_ARB_separate_shader_objects : require

#include <chroma:lighting.glsl>

uniform sampler2D MatDecSampler;
layout(location = 0) out vec2 texCoord;
layout(location = 1) flat out int cameraValid;
layout(location = 2) flat out mat4 cameraInvProj;
layout(location = 6) flat out mat4 cameraProj;
layout(location = 10) flat out vec3 cameraDown;
layout(location = 11) flat out int autoLastAddress;

void main() {
    autoLastAddress = int(chromaMdBits(MatDecSampler, 43));
    vec2 uv = vec2((gl_VertexIndex << 1) & 2, gl_VertexIndex & 2);
    gl_Position = vec4(uv * 2.0 - 1.0, 0.0, 1.0);
    texCoord = uv;
    cameraValid = chromaMdValid(MatDecSampler, 0) ? 1 : 0;
    cameraInvProj = mat4(0.0);
    cameraProj = mat4(0.0);
    cameraDown = vec3(0.0, -1.0, 0.0);
    if (cameraValid != 0) {
        cameraInvProj = chromaMdInvProj(MatDecSampler, 0);
        for (int i = 0; i < 16; i++)
            cameraProj[i / 4][i % 4] = chromaMdFloat(MatDecSampler, 1 + i);
        cameraDown = normalize(chromaMdRot(MatDecSampler, 0) * vec3(0.0, -1.0, 0.0));
    }
}
