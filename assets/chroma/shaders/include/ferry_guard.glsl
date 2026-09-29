// Only the shared camera header is protected from first-person depth clears.
// Payload packets are validated and healed individually after scene rendering.
#include <chroma:auto_transport.glsl>
bool chromaReservedPixel() {
    return ProjMat[2][3] != 0.0 &&
        chromaAutoHeaderPixel(ivec2(gl_FragCoord.xy), ivec2(ScreenSize));
}
