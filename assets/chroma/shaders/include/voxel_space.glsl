#ifndef CHROMA_VOXEL_SPACE
#define CHROMA_VOXEL_SPACE
// The caller includes minecraft:globals.glsl before this file.
#include <chroma:shadow_config.glsl>
#define CHROMA_VOX_N 256
#define CHROMA_VOX_CELLS 4
#define CHROMA_VOX_CELL 0.25
#define CHROMA_VOX_META_MAGIC 0xC70A0256u

uint chromaVoxDecode(vec4 value) {
    uvec4 b = uvec4(value * 255.0 + 0.5);
    return b.r | (b.g << 8u) | (b.b << 16u) | (b.a << 24u);
}
vec4 chromaVoxEncode(uint value) {
    return vec4(value & 255u, (value >> 8u) & 255u,
                (value >> 16u) & 255u, value >> 24u) / 255.0;
}
ivec3 chromaVoxDims() {
#if CHROMA_STATIC_WORLD
    return CHROMA_VOX_DIMS;
#else
    return ivec3(CHROMA_VOX_N);
#endif
}
ivec3 chromaVoxOrigin() {
#if CHROMA_STATIC_WORLD
    return CHROMA_VOX_ORIGIN;
#else
    return (CameraBlockPos + ivec3(floor(-CameraOffset))) * CHROMA_VOX_CELLS
        - ivec3(CHROMA_VOX_N / 2);
#endif
}
bool chromaVoxContains(ivec3 voxel, ivec3 origin) {
    ivec3 local = voxel - origin;
    return all(greaterThanEqual(local, ivec3(0))) && all(lessThan(local, chromaVoxDims()));
}
ivec3 chromaVoxOf(vec3 cameraRelativeWorld) {
    return CameraBlockPos * CHROMA_VOX_CELLS
        + ivec3(floor((cameraRelativeWorld - CameraOffset) * float(CHROMA_VOX_CELLS)));
}
vec3 chromaVoxCentre(ivec3 voxel) {
    return (vec3(voxel - CameraBlockPos * CHROMA_VOX_CELLS) + 0.5) * CHROMA_VOX_CELL
        + CameraOffset;
}
ivec3 chromaVoxStorage(ivec3 voxel) {
#if CHROMA_STATIC_WORLD
    return voxel - CHROMA_VOX_ORIGIN;
#else
    return voxel & (CHROMA_VOX_N - 1);
#endif
}
ivec2 chromaVoxTexel(ivec3 voxel) {
    ivec3 v = chromaVoxStorage(voxel);
    return ivec2(v.x / 16 + (chromaVoxDims().x / 16) * v.z, v.y);
}
uint chromaVoxShift(ivec3 voxel) {
    return uint((chromaVoxStorage(voxel).x & 15) * 2);
}
uint chromaVoxConfidence(sampler2D volume, ivec3 voxel) {
    if (!chromaVoxContains(voxel, chromaVoxOrigin())) return 0u;
    return (chromaVoxDecode(texelFetch(volume, chromaVoxTexel(voxel), 0))
            >> chromaVoxShift(voxel)) & 3u;
}
#endif
