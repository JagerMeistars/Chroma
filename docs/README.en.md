# Chroma — player guide

Coloured lights and world shadows for **Minecraft Java 26.3**. No mod is required. [Русский](README.ru.md).

## Install

1. Download `Chroma-26.3.zip` from [Releases](https://github.com/JagerMeistars/Chroma/releases/latest).
2. Put the ZIP in `minecraft/resourcepacks`, then enable **only one Chroma pack** at highest priority in **Options → Resource Packs**. Every player who wants to see the effect must enable it.
3. Enable **Improved Transparency**. After replacing the pack, press **F3+T**.

## Spawn your first lamp

You need Creative mode and cheats or operator permission. On a dedicated server, enable `enable-command-block=true`. This long summon belongs in a command block:

```mcfunction
/give @s minecraft:command_block
```

Place the block, paste the summon below **without its leading `/`**, and activate it once with a button. `~ ~2 ~` means two blocks above the command block. The other commands in this guide can be entered in chat.

```mcfunction
/summon minecraft:item_display ~ ~2 ~ {Tags:["chroma.demo","chroma.demo.warm"],Rotation:[0f,0f],billboard:"fixed",item_display:"none",view_range:4f,width:0f,height:0f,item:{id:"minecraft:paper",count:1,components:{"minecraft:item_model":"chroma:marker","minecraft:custom_model_data":{colors:[0xFFBC4D]}}},transformation:{translation:[0f,0f,0f],left_rotation:[0f,0f,0f,1f],scale:[8f,0.3f,1f],right_rotation:[0f,0f,0f,1f]}}
```

This creates an invisible warm lamp: colour `0xFFBC4D`, radius **8 blocks**, brightness **0.3**. Place it above a floor or beside a wall to see the light. A decorative lamp model is optional.

## Five light types

Set `minecraft:item_model` to one of these IDs. Reuse any model for multiple lamps; no slot numbers are needed.

| Model ID | Shape |
| --- | --- |
| `chroma:marker` | Light in every direction |
| `chroma:marker_spot_narrow` | Narrow spotlight |
| `chroma:marker_spot` | Medium spotlight |
| `chroma:marker_spot_wide` | Wide spotlight |
| `chroma:marker_dome` | Downward hemisphere; gently flickers |

## Edit or remove a lamp

Each command below affects **only the nearest example lamp within 16 blocks**. For individual lamps in a scene, give each a unique tag and use that tag in the selector. Keep `billboard:"fixed"`, `item_display:"none"` and Z scale `1f`; radius and brightness must stay positive.

```mcfunction
# Colour: 0xRRGGBB; this example is blue
/data modify entity @e[type=minecraft:item_display,tag=chroma.demo.warm,distance=..16,sort=nearest,limit=1] item.components."minecraft:custom_model_data".colors set value [0x66CCFF]
# Radius in blocks
/data modify entity @e[type=minecraft:item_display,tag=chroma.demo.warm,distance=..16,sort=nearest,limit=1] transformation.scale[0] set value 12f
# Brightness
/data modify entity @e[type=minecraft:item_display,tag=chroma.demo.warm,distance=..16,sort=nearest,limit=1] transformation.scale[1] set value 0.15f
# Change to a medium spotlight
/data modify entity @e[type=minecraft:item_display,tag=chroma.demo.warm,distance=..16,sort=nearest,limit=1] item.components."minecraft:item_model" set value "chroma:marker_spot"
# Aim down: [yaw, pitch]
/data modify entity @e[type=minecraft:item_display,tag=chroma.demo.warm,distance=..16,sort=nearest,limit=1] Rotation set value [0f,90f]
# Move two blocks above your current position
/tp @e[type=minecraft:item_display,tag=chroma.demo.warm,distance=..16,sort=nearest,limit=1] ~ ~2 ~
# Remove this one lamp
/kill @e[type=minecraft:item_display,tag=chroma.demo.warm,distance=..16,sort=nearest,limit=1]
```

Use `Rotation` to aim a spotlight. The hemisphere always points down.

| Rotation component | Values |
| --- | --- |
| Yaw | `0` south, `90` west, `-90` east, `180` north |
| Pitch | `0` horizontal, `90` down, `-90` up |

## Global settings

To edit settings, extract the pack into a folder in `resourcepacks`; `pack.mcmeta` and `assets` must be directly inside it. Enable that folder **instead of the ZIP**, edit the file, save, then press **F3+T**.

Edit `assets/chroma/shaders/include/shadow_config.glsl`:

| Setting | Default and effect |
| --- | --- |
| `CHROMA_SHADOWS_ENABLED` | `1`: shadows on; `0`: shadows off, lights stay on and pass through walls |
| `CHROMA_SHADOW_QUALITY` | `2`: normal (default); `1`: faster, coarser shadows and penumbrae |
| `CHROMA_SHADOW_PIXELATE` | `1`: pixelated light/shadows; `0`: continuous sampling |
| `CHROMA_SHADOW_PIXELS_PER_BLOCK` | `16`: subdivisions per block when pixelation is enabled |
| `CHROMA_SOURCE_SIZE` | `0.35`: source radius; larger values produce softer shadows |

For more FPS, try `CHROMA_SHADOW_QUALITY 1`; to disable shadow calculations, set `CHROMA_SHADOWS_ENABLED 0`. Save and press **F3+T**. Quality sets the map size and sample count automatically. FPS gains depend on the scene; switching shadows off does not release their reserved video memory.

Chroma's extra fog is off by default (`FOG_DENSITY 0.0` in `assets/chroma/shaders/post/shade.fsh`). Disable hemisphere flicker with `CHROMA_FLICKER_AMOUNT 0.0` in `assets/chroma/shaders/include/flicker.glsl`.

## Optional flashlight

Copy the [`datapacks/chroma_flashlight`](https://github.com/JagerMeistars/Chroma/tree/main/datapacks/chroma_flashlight) folder from the repository into your world's `datapacks` folder, then run as a player:

```mcfunction
/reload
/function chroma_flashlight:start
```

Stop with `/function chroma_flashlight:stop` before removing the datapack. It creates **one active flashlight**: a white medium spotlight, radius 16, brightness 0.3, following the owner's eyes and direction. Starting replaces the previous owner. It counts toward the light limit; fast turns may show slight following lag.

## Practical limits

- Up to **128 simultaneously rendered lamps**. Sources must be loaded and rendered; many overlapping lights can reduce FPS.
- Objects you have not looked at may cast incorrect shadows. Look at an area after moving or changing blocks there. Press **F3+T** after changing worlds or dimensions.
- Chroma uses the surface's existing colour and texture; its brightness also depends on vanilla lighting.
- Everything is **visual**: block-light levels and mob spawning do not change.
