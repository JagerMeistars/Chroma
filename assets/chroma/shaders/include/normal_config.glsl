#ifndef CHROMA_NORMAL_CONFIG
#define CHROMA_NORMAL_CONFIG
#include <chroma:settings.glsl>
#if CHROMA_NORMAL_MAPS != 0 && CHROMA_NORMAL_MAPS != 1
#error CHROMA_NORMAL_MAPS must be 0 or 1
#endif
#endif
