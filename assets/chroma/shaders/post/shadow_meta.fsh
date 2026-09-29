#version 450
#extension GL_ARB_separate_shader_objects : require
#include <minecraft:globals.glsl>
#include <chroma:lighting.glsl>
#include <chroma:voxel_space.glsl>

uniform sampler2D MatDecSampler;
layout(location = 0) out vec4 fragColor;

// Eight words per source: world block XYZ, fractional XYZ in 1/4096 blocks,
// trace radius float bits, valid=1. Keep world integers separate from floats
// so moving the camera far from world zero cannot change the cache identity.
void main() {
    int texel = int(gl_FragCoord.x);
    int lamp = texel / 8;
    int field = texel & 7;
    uint value = 0u;
    if (lamp < CHROMA_LAMPS && chromaMdValid(MatDecSampler, 0)
            && chromaMdLampOn(MatDecSampler, lamp)) {
        vec3 relative = transpose(chromaMdRot(MatDecSampler, 0))
                      * chromaMdLampEyeOf(MatDecSampler, lamp) - CameraOffset;
        float radius = chromaMdLampRadiusOf(MatDecSampler, lamp) * CHROMA_RADIUS_GAIN;
        if (!any(isnan(relative)) && !any(isinf(relative))
                && !isnan(radius) && !isinf(radius)) {
            vec3 whole = floor(relative);
            ivec3 fraction = ivec3(floor((relative - whole) * 4096.0 + 0.5));
            ivec3 block = CameraBlockPos + ivec3(whole) + fraction / 4096;
            fraction = fraction & ivec3(4095);
            if (field < 3) value = uint(block[field]);
            else if (field < 6) value = uint(fraction[field - 3]);
            else if (field == 6) value = floatBitsToUint(max(radius, 0.001));
            else value = 1u;
        }
    }
    fragColor = chromaVoxEncode(value);
}
