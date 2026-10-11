#ifndef CHROMA_NORMAL_CONFIG
#define CHROMA_NORMAL_CONFIG
// Material relief: 0 off, 1 on. Reload resources with F3+T after editing.
#define CHROMA_NORMAL_MAPS 1
// Relief strength. 0.0 is flat; 1.0 uses the prepared normal map.
#define CHROMA_NORMAL_STRENGTH 1.0
#if CHROMA_NORMAL_MAPS != 0 && CHROMA_NORMAL_MAPS != 1
#error CHROMA_NORMAL_MAPS must be 0 or 1
#endif
#endif
