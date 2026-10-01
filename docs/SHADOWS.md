# Shadows

World-space shadows for **Minecraft Java 26.3**. Dynamic is the main edition. It uses geometry observed by the camera and supports moving light sources. No mod is required.

## Use

- Enable the Chroma resource pack and **Improved Transparency**.
- Up to 128 rendered lights; five reusable shapes and no source-slot setup.
- Commands and shader settings: [English guide](README.en.md) · [Русское руководство](README.ru.md).

## Limits

- Lighting is visual only. It does not change Minecraft block-light levels or mob spawning.
- Dynamic remembers observed geometry in a moving 64-block area. Hidden blocks and unseen edits cannot cast reliable shadows. A moved model can leave a shadow until the empty area is seen.
- The source entity must be rendered. Entity culling in some mod setups can hide a light; disabling entity culling fixes it.
- High light overlap and shadow samples can lower FPS. Reduce `CHROMA_SHADOW_SAMPLES` in `shadow_config.glsl` to 8 for a faster, rougher result.
- Chroma adds light independently of vanilla brightness. Very bright surfaces can clip to white.

## Editions

- **Dynamic** — moving world shadows; main release.
- **Auto** — lights without shadows; archived on [`codex/auto`](https://github.com/JagerMeistars/Chroma/tree/codex/auto).
- **Static** — exported shadows for one prepared world; see [export notes](SHADOW_VALIDATION.md).
