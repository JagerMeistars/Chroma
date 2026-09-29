# Chroma — automatic lights

Chroma adds coloured point lights, three spotlight widths, downward hemispheres, soft glow and blue-grey distance fog to **Minecraft Java 26.3**. It uses a vanilla resource pack, format **97.1**, with no required mod or datapack. **Auto** is the main shadow-free edition; this branch also provides **Shadows Dynamic** and **Shadows Static**. The same commands and 128-source budget apply to all three. Read the [shadow guide](SHADOWS.md) before choosing a shadow edition. Distance fog remains visible without light sources.

## Install and create a light

1. Put `Chroma-Auto-26.3.zip`, `Chroma-Shadows-Dynamic-26.3.zip`, or the world-specific `Chroma-Shadows-Static-objCubed-26.3.zip` in `minecraft/resourcepacks`. An unpacked folder also works; `pack.mcmeta` and `assets` must be at its root.
2. Enable **only one Chroma edition**, at highest priority, in **Options → Resource Packs**. Initially test it on its own. Other packs that override core shaders or `minecraft:post_effect/end_of_frame.json` require a deliberate merge. RPDREVO is not required.
3. After replacing pack files, press **F3+T**. For shadow editions, also reload after changing worlds or dimensions to reset the cache. Static must match the exported world/dimension. The old 26.2 Fabulous installation procedure does not apply.
4. In a world where you have command permission, create a source above a pale floor:

```mcfunction
/summon minecraft:item_display ~ ~2 ~ {Tags:["chroma.demo","chroma.demo.warm"],billboard:"fixed",item_display:"none",view_range:4f,width:0f,height:0f,item:{id:"minecraft:paper",count:1,components:{"minecraft:item_model":"chroma:marker","minecraft:custom_model_data":{colors:[16759885]}}},transformation:{translation:[0f,0f,0f],left_rotation:[0f,0f,0f,1f],scale:[8f,0.3f,1f],right_rotation:[0f,0f,0f,1f]}}
```

Use a command block if the command is too long for chat; omit the leading `/` there. This makes a warm `#FFBC4D` light with an 8-block nominal radius and brightness `0.3`. Every player who should see it must enable the pack.

**Reuse `chroma:marker` for as many point lights as you need within the 128-source budget.** There is no model number to reserve or assign. A light uses one `item_display`; its model contains two small technical quads. These carry shader data and do not draw a visible fixture. A decorative lamp block/model is optional and separate.

## Colours, size and shape

| Setting | Meaning |
| --- | --- |
| `minecraft:custom_model_data.colors[0]` | RGB colour as `R*65536 + G*256 + B`. White: `16777215`; red: `16711680`; green: `65280`; blue: `255`. Default: white. |
| `transformation.scale[0]` (X) | Nominal radius in blocks. Keep positive. |
| `transformation.scale[1]` (Y) | Brightness. Start with `0.1f`–`0.5f`; keep positive. |
| `transformation.scale[2]` (Z) | Leave at `1f`. |
| `item_display:"none"`, `billboard:"fixed"` | Keep these settings for predictable marker geometry and direction. |

| Item model | Light shape |
| --- | --- |
| `chroma:marker` | Point light in all directions. |
| `chroma:marker_spot_narrow` | Narrow spotlight, approximately 16° outer half-angle. |
| `chroma:marker_spot` | Medium spotlight, approximately 28° outer half-angle. |
| `chroma:marker_spot_wide` | Wide spotlight, approximately 42° outer half-angle. |
| `chroma:marker_dome` | Hemisphere pointing down in world coordinates. |

Every model can be reused by multiple sources, including coincident sources. Colour, position, radius, brightness and direction remain independent. The numbered model names from the earlier pack are retained only as compatibility aliases; their numbers no longer allocate lighting slots.

Spotlights follow the display's rotation. Set `left_rotation:[0.7071068f,0f,0f,0.7071068f]` to point a spotlight down (positive 90° around X). A negative X quaternion points it up. Domes always face world-down, regardless of display rotation. Glow uses a spherical approximation for every shape.

All dome lights flicker gently. Their phase is derived from colour, so automatic collection order does not change it. Point lights and spotlights are steady. To disable dome flicker, set `CHROMA_FLICKER_AMOUNT` to `0.0` in `assets/chroma/shaders/include/flicker.glsl`, then reload the pack.

## Edit and remove

These commands select the nearest warm demo light. Tags are ordinary command selectors, not lighting IDs; choose convenient tags for your scene.

```mcfunction
# Blue colour
/data modify entity @e[type=minecraft:item_display,tag=chroma.demo.warm,sort=nearest,limit=1] item.components."minecraft:custom_model_data".colors set value [6737151]
# Radius and brightness
/data modify entity @e[type=minecraft:item_display,tag=chroma.demo.warm,sort=nearest,limit=1] transformation.scale[0] set value 12f
/data modify entity @e[type=minecraft:item_display,tag=chroma.demo.warm,sort=nearest,limit=1] transformation.scale[1] set value 0.15f
# Change the shape
/data modify entity @e[type=minecraft:item_display,tag=chroma.demo.warm,sort=nearest,limit=1] item.components."minecraft:item_model" set value "chroma:marker_dome"
# Move above your position
/tp @e[type=minecraft:item_display,tag=chroma.demo.warm,sort=nearest,limit=1] ~ ~2 ~
# Remove only the demo sources in this dimension
/kill @e[type=minecraft:item_display,tag=chroma.demo]
```

Removing the entity turns its light off when that change reaches the rendered frame. The new renderer does not retain old lamp data for a grace period. Keep both X/Y scales positive; to switch off a light, remove its entity instead of collapsing its model.

[examples.mcfunction](examples.mcfunction) contains creation, editing and cleanup references. Copy only the section you need; it is not a required datapack. [examples-128.mcfunction](examples-128.mcfunction) creates an 16 × 8 grid with 128 colours and all five shapes, using only the five reusable model names. Run its commands once from the **same origin** above a floor, without other active Chroma sources. To remove that grid:

```mcfunction
/kill @e[type=minecraft:item_display,tag=chroma.test128]
```

## 128-light test datapack

A test datapack is installed in the `objCubed` save at `datapacks/chroma_test_128`. After enabling/reloading Chroma with **F3+T**, run `/reload` once in the world, then `/function chroma_test:spawn128`. It clears its own previous test lights and spawns a 16 × 8 grid around the command position. Cleanup: `/function chroma_test:clear128`.

## How the new renderer works

The marker's texture identifies its shape; tint and transformed geometry provide the other light parameters. The renderer takes the marker's current-frame vertex address, writes its data into a sparse GPU catalogue, counts valid entries and compacts them into a working list of up to 128 sources. Users do not supply addresses. This is not random hashing, and unrelated colours do not compete for a shared hand-assigned slot.

A `128 × 72` grid stores which sources can affect each screen tile. Each tile uses four 32-bit masks to cover the 128-source list. The final pass reads only those sources and combines surface light and glow in one loop. Camera matrices are decoded at the screen-triangle vertices rather than again at every pixel. Light parameters are collected afresh each frame. Shadow editions additionally cache world geometry and source-centred distance maps; see [how shadows work](SHADOWS.md).

## Limits and troubleshooting

- **Capacity is 128 simultaneously rendered sources.** The names can be reused freely, but the working list is finite. Above 128, some sources are omitted; do not rely on a particular selection order.
- **Sources must be rendered.** Chunk loading, server entity tracking, view distance and renderer culling still apply. The example's zero display width/height and increased view range help, but do not make unloaded entities visible to shaders.
- **No light:** test the exact first command near a pale, textured floor with only Chroma enabled. Keep the marker's X/Y scales positive. A paper item in inventory/hand is the intended fallback, not a placed source.
- **Occlusion depends on the edition.** Auto passes through walls. Dynamic can shadow cached, previously observed geometry inside its moving 64-block window; unseen geometry or unseen edits are unknown. Removing every lamp does not clear its geometry cache; **F3+T** does. Static shadows use only exported geometry and bounds, including off-camera blockers; re-export after block changes. See [shadow limits](SHADOWS.md). Block-light levels, mob spawning and other mechanics remain unchanged.
- **Shadows affect direct surface light.** The weak existing analytic glow is unshadowed and can bleed through blockers. To disable it, set `VOL_STRENGTH` to `0.0` in `assets/chroma/shaders/post/shade.fsh`, then rebuild/reload.
- **Hands and HUD keep vanilla lighting.** In shadow editions, the actual pixels covered by first-person hands/held items and the separate 3D-HUD pass are excluded from Chroma shading and voxel observations. They do not become world blockers. The surrounding world remains eligible; there is no fixed screen rectangle excluded. The ordinary 2D GUI stays unchanged.
- **Performance depends on overlap and resolution.** Widely separated sources benefit most from tile culling. If all 128 affect the same pixels, those pixels still evaluate all 128; shadows add map updates and filtering. See [Auto validation](VALIDATION.md) and the separate [shadow results](SHADOW_VALIDATION.md) for measured conditions; neither is a universal FPS promise.
- **Transparent surfaces and depth edges** may show screen-space approximations. Fog can be reduced with `FOG_DENSITY`/`FOG_SKY`, and glow with `VOL_STRENGTH`, in `assets/chroma/shaders/post/shade.fsh`.
- **Transport has a finite address space.** The sparse catalogue supports up to 65,536 raw vertex addresses, further bounded by the rendered image size. This is an internal transport bound, not a number to assign to lamps. Very small render sizes or unusually heavy visible model geometry can exceed it. The old 576-pixel-height requirement is gone; a 320 × 240 frame has approximately 6,240 raw addresses. Reduce visible model complexity or increase render resolution if this bound is reached.
- **Reload errors/conflicts:** inspect `minecraft/logs/latest.log`; test Chroma alone first. Render-altering mod compatibility requires separate verification.
