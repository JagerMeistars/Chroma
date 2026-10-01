#ifndef CHROMA_SHADOW_CONFIG
#define CHROMA_SHADOW_CONFIG
// Shadows: 0 off, 1 on. Reload resources (F3+T) after editing.
#define CHROMA_SHADOWS_ENABLED 1
// Quality: 1 faster (64x64 maps, 8 filter taps), 2 normal (128x128, 16).
#define CHROMA_SHADOW_QUALITY 2
#if CHROMA_SHADOWS_ENABLED != 0 && CHROMA_SHADOWS_ENABLED != 1
#error CHROMA_SHADOWS_ENABLED must be 0 or 1
#endif
#if CHROMA_SHADOW_QUALITY == 1
#define CHROMA_SHADOW_MAP_SIZE 64
#define CHROMA_SHADOW_SAMPLES 8
#elif CHROMA_SHADOW_QUALITY == 2
#define CHROMA_SHADOW_MAP_SIZE 128
#define CHROMA_SHADOW_SAMPLES 16
#else
#error CHROMA_SHADOW_QUALITY must be 1 or 2
#endif
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
#define CHROMA_SHADOW_PIXELATE 1
// Shared light/shadow subdivisions per block; independent of voxel resolution.
#define CHROMA_SHADOW_PIXELS_PER_BLOCK 16
#define CHROMA_SHADOW_STEPS 768
#define CHROMA_SHADOW_DEBUG 0
#endif
