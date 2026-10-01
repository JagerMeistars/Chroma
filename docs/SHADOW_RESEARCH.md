# Research notes

Chroma is a vanilla resource pack for Minecraft 26.3. Its post effect receives camera-visible, already-lit scene colour and depth. A pack cannot recover geometry the renderer culled or exact unlit material colour after vanilla lighting; Dynamic therefore keeps an observed world-space surface cache and the light pass uses an independent additive response.

The current release uses world-space entity shadows. Screen-space entity shadows were rejected because they move with the camera and fail when an object leaves the frame. VacancyBounds1b accelerates removal checks while retaining exact tests where visibility is uncertain. Its previous-scene measurements are summarized in [validation](SHADOW_VALIDATION.md).

[Player guide](README.en.md) · [Shadow notes](SHADOWS.md) · [Build checks](../tools/README.md)
