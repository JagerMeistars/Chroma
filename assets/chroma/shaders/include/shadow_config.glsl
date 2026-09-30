#ifndef CHROMA_SHADOW_CONFIG
#define CHROMA_SHADOW_CONFIG
// Dynamic observed-world cache. The static exporter replaces this small file.
#define CHROMA_STATIC_WORLD 0
// Dynamic particle exclusion requires Improved Transparency ON. Set 0 for
// classic transparency: native particles stay visible but can cast shadows.
#define CHROMA_PARTICLE_DEPTH_MASK 1
#define CHROMA_SOURCE_SIZE 0.35
#define CHROMA_SHADOW_PIXELATE 1
// Shared light/shadow subdivisions per block; independent of voxel resolution.
#define CHROMA_SHADOW_PIXELS_PER_BLOCK 16
#define CHROMA_SHADOW_STEPS 768
#define CHROMA_SHADOW_DEBUG 0
#endif
