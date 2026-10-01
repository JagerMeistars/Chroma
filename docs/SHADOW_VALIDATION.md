# Validation

## Chroma 26.3

The current pack is **WorldEntities2**. The world-shadow geometry is the accepted WorldEntities1/VacancyBounds1b version; the release adds the inventory marker and independent-light fixes.

- Vanilla 26.3 inventory test: ten wool icons matched vanilla RGB exactly. The old light-blue icon was distorted.
- Light test: 84 fixed surface points in night, daylight and torch conditions. With Chroma enabled, the measured added colour changed by at most 1/255 between night and daylight and 4/255 across all three conditions. The original effect varied by as much as 90/255.
- Five source shapes rendered with the expected colour, radius and intensity.
- Native pipeline: 32 shader files compiled, 232 stages translated and 116 OpenGL links passed. Command examples parsed without errors.
- FPS was not remeasured for this release. Earlier timings below are from WorldEntities1's separate horse scene and are not a general performance promise.

## Earlier WorldEntities1 performance check

Vanilla Minecraft 26.3, RTX 4060 Ti, 1920×1080, one stationary lamp and a moving horse. VacancyBounds1b changed average FPS from 44.11 to 56.78, 1% low from 10.69 to 26.46, and P99 frame time from 89.78 to 33.17 ms. This is a result for that scene only.

Static export excludes entities, glass and water. Dynamic shadows also have the observation limits described in [Shadow notes](SHADOWS.md).
