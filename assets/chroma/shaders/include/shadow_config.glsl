#ifndef CHROMA_SHADOW_CONFIG
#define CHROMA_SHADOW_CONFIG
// Dynamic observed-world cache. The static exporter replaces this small file.
#define CHROMA_STATIC_WORLD 0
// Dynamic particle exclusion requires Improved Transparency ON. Set 0 for
// classic transparency: native particles stay visible but can cast shadows.
#define CHROMA_PARTICLE_DEPTH_MASK 1
// Improved Transparency only: visible OIT fragments neither cast nor receive
// Dynamic light/shadows. Alpha-zero holes keep the native background depth.
// Set 0 to restore native transparent receiver/caster depth; Static is native.
#define CHROMA_TRANSPARENT_DEPTH_MASK 1
// Entity-shader models (also some block entities/special items): 0 no casting,
// 1 persistent world cache, 2 screen-space casting. Modes 0/2 require Improved
// Transparency ON and TRANSPARENT_DEPTH_MASK=1; otherwise native/cache behavior.
#define CHROMA_ENTITY_SHADOWS 1
#define CHROMA_ENTITY_SHADOW_DISTANCE 4.0
#define CHROMA_ENTITY_SHADOW_STEPS 24
#define CHROMA_SOURCE_SIZE 0.35
// Dynamic PCSS disk taps: 16 by default; 8 is an optional lower-density filter.
#define CHROMA_SHADOW_SAMPLES 16
#define CHROMA_SHADOW_PIXELATE 1
// Shared light/shadow subdivisions per block; independent of voxel resolution.
#define CHROMA_SHADOW_PIXELS_PER_BLOCK 16
#define CHROMA_SHADOW_STEPS 768
#define CHROMA_SHADOW_DEBUG 0
#endif
