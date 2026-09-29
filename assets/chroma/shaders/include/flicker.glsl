#ifndef CHROMA_FLICKER_GLSL
#define CHROMA_FLICKER_GLSL
#define CHROMA_FLICKER_AMOUNT 0.12
#define CHROMA_FLICKER_SPEED 0.9
// Colour gives a stable phase without assigning an identity to the source.
// Compaction order, camera movement and unrelated entities cannot change it.
float chromaSourceFlicker(int shape, vec3 colour, float time) {
    if (shape != 4) return 1.0;
    float phase = dot(colour, vec3(17.0, 43.0, 71.0));
    float wave = sin(time * CHROMA_FLICKER_SPEED + phase)
               * sin(time * CHROMA_FLICKER_SPEED * 0.591 + phase * 0.413);
    return 1.0 - CHROMA_FLICKER_AMOUNT * (0.5 + 0.5 * wave);
}
#endif
