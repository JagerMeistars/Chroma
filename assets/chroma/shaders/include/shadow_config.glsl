#ifndef CHROMA_SHADOW_CONFIG
#define CHROMA_SHADOW_CONFIG
#include <chroma:settings.glsl>
// Internal shadow layout and validation. User settings are in settings.glsl.
#if CHROMA_ADAPTIVE_SHADOWS != 0 && CHROMA_ADAPTIVE_SHADOWS != 1
#error CHROMA_ADAPTIVE_SHADOWS must be 0 or 1
#endif
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
// Backend constants: changing these requires matching core/atlas support.
#define CHROMA_STATIC_WORLD 0
// OIT particle and transparent-depth exclusion protocol.
#define CHROMA_PARTICLE_DEPTH_MASK 1
#define CHROMA_TRANSPARENT_DEPTH_MASK 1
// Entity-shader models use the persistent world cache in this pack.
#define CHROMA_ENTITY_SHADOWS 1
#define CHROMA_ENTITY_SHADOW_DISTANCE 4.0
#define CHROMA_ENTITY_SHADOW_STEPS 24
#define CHROMA_SHADOW_STEPS 768
#if CHROMA_FILTER_SAMPLES_OVERRIDE == 8 || CHROMA_FILTER_SAMPLES_OVERRIDE == 16
#undef CHROMA_SHADOW_SAMPLES
#define CHROMA_SHADOW_SAMPLES CHROMA_FILTER_SAMPLES_OVERRIDE
#elif CHROMA_FILTER_SAMPLES_OVERRIDE != 0
#error CHROMA_FILTER_SAMPLES_OVERRIDE must be 0, 8 or 16
#endif
#if CHROMA_SHADOW_REFRESH_FRAMES != 1 && CHROMA_SHADOW_REFRESH_FRAMES != 8
#error CHROMA_SHADOW_REFRESH_FRAMES must be 1 or 8
#endif
#define CHROMA_SHADOW_DEBUG 0
#endif
