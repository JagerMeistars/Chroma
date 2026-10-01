# Minecraft 26.3 shadow research / Исследование теней Minecraft 26.3

Evidence filenames below refer to the local `audit/shadows/` directory. Raw reports, captures and bytecode extracts are excluded from Git and resource-pack ZIPs; they are not downloadable links. / Имена материалов ниже относятся к локальной папке `audit/shadows/`. Исходные отчёты, снимки и извлечённый байткод не входят в Git и ZIP ресурспака; это не ссылки для скачивания.

Research snapshot: **2026-10-01**. The corrected world-entity test identifies motion-related spikes in **`voxel_update`**. Earlier EntityScreen4/EmptyRegion gains concerned screen mode `2` and do **not** fix the user's world-caster stall. The current main edition, **WorldEntities2**, retains WorldEntities1 mode `1` and VacancyBounds1b: a single-level conservative tile-depth bound reduces the measured update spikes while preserving world entity casters. / Исправленный тест мировых теней сущностей выявил всплески **`voxel_update`** при движении. Прежнее ускорение EntityScreen4/EmptyRegion относилось к экранному режиму `2` и **не исправляет** просадку мировых теней пользователя. Текущая основная версия **WorldEntities2** сохраняет режим `1` и VacancyBounds1b из WorldEntities1: одноуровневая консервативная сводка глубины тайлов уменьшает измеренные всплески обновления, сохраняя сущности как мировые препятствия.

Shadow-free Auto is preserved on `codex/auto`; current WorldEntities development is on `main`. / Прежний Auto без теней сохранён в `codex/auto`; текущий WorldEntities развивается в `main`.

WorldEntities2 adds marker-identity and ambient-independent additive-light fixes shared by Dynamic and Static; Static shadow geometry is unchanged. The timings and parity results below retain their historical build labels and are not new WorldEntities2 measurements. / WorldEntities2 исправляет распознавание маркеров и независимость добавляемого света от фонового освещения в Dynamic и Static; геометрия теней Static не изменена. Замеры и сравнения ниже сохраняют названия проверенных прежних сборок и не являются новыми замерами WorldEntities2.

## Evidence / Источники

The inspected client is the installed `minecraft-26.3-client.jar`, SHA-256 `4508d006323f24fa02876310c192d739af56516eb259000ac50f0909a68c9a2d`. Its absolute path, mod hashes, extraction time and evidence hashes are in the manifest (`horse-engine/research-manifest.json`). Evidence was obtained with `javap -p -c -cp <jar> <class>` and direct ZIP-member reads, without running the client or GPU. Bytecode omissions are marked explicitly.

| Evidence | Contents |
| --- | --- |
| Framegraph (`horse-engine/research-framegraph.javap.txt`) | `net.minecraft.client.renderer.LevelTargetBundle`, `GameRenderer`, `LevelRenderer`, `PostChain`: external target visibility and validation |
| Post API (`horse-engine/research-post-api.javap.txt`) | `net.minecraft.client.renderer.PostChainConfig$Pass/$InternalTarget/$TargetInput`, `PostChain`, `PostPass`, `ShaderManager`: pass schema, bindings, attachments and draw |
| Pipelines (`horse-engine/research-pipelines.javap.txt`) | `net.minecraft.client.renderer.RenderPipelines`: entity, armour, blob-shadow and OIT pipeline definitions |
| Horse (`horse-engine/research-horse.javap.txt`) | `EntityModel`, horse renderer/layers, `LivingEntityRenderer`, `ModelFeatureRenderer`: actual material and geometry routes |
| Blob shadow (`horse-engine/research-blob.javap.txt`) | `net.minecraft.client.renderer.rendertype.RenderTypes` and `feature.ShadowFeatureRenderer`: ground-patch construction |
| Mods (`horse-engine/research-mods.javap.txt`) | Relevant Sodium, EMF and ETF methods; direct pipeline-reference scan is in the manifest |
| Outline pass (`horse-engine/research-outline.javap.txt`) | Model duplication, glowing/culling gates, colour-only geometry pass, indexed draws and outline-to-main scheduling |
| Shader contracts (`horse-engine/research-shader-contracts.txt`) | Native camera/draw uniforms, blob shaders and OIT outputs |

## English

### What changed in 26.3

The official release notes describe a new OIT algorithm, terrain MultiDrawIndirect, ShaderC compilation on both graphics backends, explicit shader locations, and the always-on `minecraft:end_of_frame` effect. They also document `integrate_depth` for HUD/gizmo depth. These are useful rendering changes; they do not document a new resource-pack light camera or entity-geometry input. [Official 26.3 release notes](https://feedback.minecraft.net/hc/en-us/articles/48913133328013-Minecraft-Java-Edition-26-3).

### What a vanilla resource pack can access

* **Current main colour and depth.** `GameRenderer` loads end-of-frame effects with `LevelTargetBundle.MAIN_TARGETS`, containing only `minecraft:main`. `LevelTargetBundle.get/replace` recognise `main` and `entity_outline`; the outline target is offered to the dedicated outline chain, not to end-of-frame effects. Declaring another external name fails `PostChain.load` validation. Framegraph evidence (`horse-engine/research-framegraph.javap.txt`).
* **Its own post targets and passes.** `PostChainConfig.Pass` selects vertex/fragment shaders, sampler inputs, uniform blocks and one output. `PostPass` attaches one colour target and draws a fullscreen triangle. Internal targets use RGBA8 colour plus the default depth attachment; dimensions can be fixed or inherit the frame, and targets may persist. The JSON interface does not expose compute dispatch, storage-buffer bindings, multiple colour outputs, or replaying entity geometry from a light. Backend capabilities alone do not add those resource-pack bindings. Post API (`horse-engine/research-post-api.javap.txt`).
* **Existing core shader inputs.** Entity vertices provide position, colour, UVs/lightmap/overlay coordinates and normal. Native draw uniforms contain matrices, colour modulation and an offset; global uniforms contain camera/time/screen data. There is no semantic mob ID, skeleton or complete entity mesh in those inputs. `ModelFeatureRenderer.prepareModel` applies animation and sends model vertices through `Model.renderToBuffer` on the CPU. Horse evidence (`horse-engine/research-horse.javap.txt`), shader contracts (`horse-engine/research-shader-contracts.txt`).

OIT has additional **internal** `depth_bounds`, `depth_bounds_culled`, transmittance, accumulation, cloud-depth and terrain-depth resources. They are not names accepted by the post target bundle. Their contents also serve a different purpose: translucent depth bounds, combined transmittance coefficients and accumulated colour in the current camera view, not per-entity geometry. A core OIT shader can use its existing bindings; that does not make those resources available to an arbitrary post pass. Framegraph (`horse-engine/research-framegraph.javap.txt`), OIT shader outputs (`horse-engine/research-shader-contracts.txt`).

### Existing glowing-entity pass: useful, but conditional

The extra pass is real. In 26.3 there is no `OutlineBufferSource` class: `SubmitNodeCollection.submitModel` submits the ordinary model first, then the same animated model/state/pose to the outline phase when its outline colour is nonzero and the material supports outlines. The core override is `rendertype_outline`, with position, UV and colour; its bindings include camera/draw uniforms and the skin texture, but no Chroma light catalogue. Outline bytecode and native shaders (`horse-engine/research-outline.javap.txt`).

* **Activation requires game state.** `Minecraft.shouldEntityAppearGlowing` requires glowing, except for the spectator-player-outline shortcut. An RP cannot set that flag for ordinary mobs. Automatically enabling this route would require a server command/datapack/mod; that is an explicit dependency, not a standalone-RP solution. The outline phase also requires a player/non-panoramic view. Distance, frustum and section visibility checks still happen before submission.
* **A ferry into main is possible.** The dedicated outline post chain receives `OUTLINE_TARGETS = {minecraft:main, minecraft:entity_outline}`. It can process outline data into its own targets and write reserved data into main. Its processing and native outline composite precede the main post effects, including end-of-frame. Such a design must deliberately suppress or preserve the normal glowing contour/composite, protect transport cells and handle frames without any outlined submissions; this has not been implemented or tested.
* **This is not an existing light-depth pass.** `LevelRenderer.executeOutline` clears/draws the outline colour attachment with **no depth attachment**, using an unblended colour target. Reprojecting vertices and writing fragment depth therefore cannot resolve nearest surfaces where triangles overlap. The RP cannot change that attachment or blend equation. Encoding a mesh into nonoverlapping raster cells and resolving visibility in later fragment passes is a possible research direction, with new storage, capacity and cost requirements.
* **Indices are frame geometry addresses, not entity identity.** `PreparedRenderType.draw` uses indexed draws with one instance and `baseVertex = vertexOffset / vertexStride`. This offers vertex-index addressing, but no semantic entity ID or stable cross-frame mesh index. Primitive numbering alone cannot identify models across draws. The outline batch can include multiple models, layers and materials; layout/collision assumptions require an actual draw capture. GPU support or transport correctness was not tested here.

This route could provide animated geometry hidden behind scene depth for **submitted, explicitly glowing** entities while preserving their normal body draw. It does not provide off-frustum mobs, a free shadow map, or a transparent replacement for the current pure-RP mode.

### Horse and installed-mod routes

| Surface | Verified native route | Consequence for current Chroma metadata |
| --- | --- | --- |
| Ordinary horse body | Default `EntityModel` function → `RenderTypes.entityCutout` → `core/entity` | Unblended `ColorTargetState.DEFAULT`; opaque surviving fragments are eligible for the entity alpha tag. |
| Armour and saddle | `HorseRenderer` equipment layers → `EquipmentLayerRenderer` → `armorCutoutNoCull` or its glint variant | Same entity shader family and unblended colour target; no separate horse-only shader bypass was found. |
| Coat markings | `HorseMarkingLayer.submit` → `entityTranslucent` | Uses OIT with Improved Transparency ON; current transparent-depth policy marks covered pixels unknown rather than entity casters/receivers. |
| Vanilla circular shadow | `ShadowFeatureRenderer` → `entityShadow` → `core/rendertype_entity_shadow` | Separate translucent/OIT shader, with normal blob pipeline depth writes disabled. CPU-built ground patches carry radius/UV/alpha, not the animated body silhouette. |

Routes and blend states: horse (`horse-engine/research-horse.javap.txt`), pipelines (`horse-engine/research-pipelines.javap.txt`), blob (`horse-engine/research-blob.javap.txt`). The current OIT compositor's depth mask can also exclude floor pixels covered by the vanilla blob. This is a rendering limitation to inspect, not an established cause of the slowdown.

The installed versions inspected were **Sodium 0.9.3-alpha.1**, **EMF 3.3.8** and **ETF 7.2.4**, all for 26.3. Sodium's entity fast path emits transformed vertices and preserves the supplied colour; its blob mixin accelerates ground-quad generation. Its packaged shaders and direct pipeline changes concern terrain, and its shader blacklist does not include `entity.fsh`. EMF's inspected living-renderer changes concern models, animation and texture choice. No direct entity blend/pipeline replacement was found in these inspected paths. This is a static finding, not blanket compatibility certification. Mod evidence (`horse-engine/research-mods.javap.txt`), scan and hashes (`horse-engine/research-manifest.json`).

ETF can add **emissive overlays** using `entityTranslucent`, or `beaconBeam(texture, true)` in BRIGHT mode. A custom texture/model pack can therefore use additional routes; an actual draw capture is needed to establish which are active for a particular horse. Those routes must not be assumed to carry the opaque entity tag.

### Practical choices and the next decision

| Option | What it can improve | Remaining constraint / status |
| --- | --- | --- |
| Current bounded screen contact ray | Shadows of visible entity surfaces without persistent moving-mob geometry | Camera-visible depth only; hidden geometry, thin silhouettes and discrete depth remain limits. Implemented; the measured horse-scene cost is separated below. |
| Perspective-correct screen DDA | Avoid repeated/skipped screen pixels caused by uniform world-distance steps | Needs a bounded traversal and native reversed-depth validation; not an established fix for this slowdown. |
| Conservative entity-presence/depth hierarchy, then screen traversal | Skip screen regions that provably contain no relevant entity evidence | Feasible with ordinary post passes/targets; requires new code and measured comparison. It cannot recover unseen surfaces. |
| Lower-resolution contact result with depth-aware reconstruction | Reduce repeated shading work | Additional passes and edge/thin-feature errors; not implemented or validated here. |
| Observed world geometry cache | Retain previously seen surfaces outside the current view | Moving-body history, acquisition cost and finite geometry capacity remain. Returning mobs to that cache is not an established fix. |
| Vanilla blob | Cheap approximate ground contact | Circular footprint, no arbitrary-light silhouette or wall shadow; not equivalent to the requested lighting. |
| A renderer extension or explicitly supplied proxy geometry | Supply stable entity geometry or an actual light-view pass | Beyond the native RP interface; proxy shapes would remain approximations. |

Two primary references support the algorithm choices, not a diagnosis of this scene. McGuire and Mara's [Efficient GPU Screen-Space Ray Tracing](https://jcgt.org/published/0003/04/04/paper.pdf) describes perspective-correct DDA with contiguous screen sampling instead of uniform 3D steps. AMD's [FidelityFX SSSR](https://gpuopen.com/fidelityfx-sssr/) demonstrates hierarchical depth traversal. Its SDK uses HLSL wave operations and a GPU integration/compute pipeline; it is not a drop-in vanilla resource pack. A Chroma adaptation would need the available fragment-pass interface and separate correctness/performance checks.

In the current [shade shader](../assets/chroma/shaders/post/shade.fsh), a tagged entity receiver skips `chromaEntityShadow` but still evaluates world `chromaShadow`. Consequently, a correctly tagged horse filling more of the frame does not automatically mean more screen-contact rays. A tag/layer mismatch, the world filter and persistent-cache work must be distinguished before replacing the screen algorithm.

### Corrected diagnosis: moving world entity, mode 1

The user requires world entity casters, not screen shadows. The new frame-time test (`world-horse-mode1-moving-fps-150331.json`) explicitly uses mode `1`, one original stationary spotlight and the saved armoured horse. Original world mode measures **41.81 FPS / 10.15 FPS 1% low / 91.79 ms P99** during movement; EmptyRegion gives **44.33 / 9.44 / 96.90 ms**, so it does not resolve the stall.

The separate GPU profile (`world-horse-gpu-mode1-150543.json`) isolates the spikes to geometry updates:

| World mode 1 | `voxel_update` mean / P95 / max, ms | `shade` mean, ms |
| --- | ---: | ---: |
| Original, stationary horse | 6.59 / 10.18 / 13.53 | 6.59 |
| Original, moving horse | **13.32 / 53.60 / 108.54** | 6.27 |
| EmptyRegion, moving horse | 14.23 / 70.44 / 86.98 | 6.50 |

Scope: vanilla 26.3, 1920×1080, verified 32/32, native blob/bob/Improved Transparency ON; primary PID 43724 remained active. Controlled native motion used ±0.12-block displacement and ±25° rotation; collision could push the player, so this is not a camera-locked test. Frame timing and GPU profiling were separate. The accepted 1b path uses a single `256 × 256` current-frame depth bound to accelerate exact vacancy proofs, retaining mode `1` and **no screen-shadow ray**. Uncertain tiles retain exact native-pixel checks; no stale-data expiry is introduced.

**Accepted WorldEntities1 / VacancyBounds1b:** the fresh moving mode-1 pair (`world-horse-vacancy1b-moving-fps-152250.json`) improves average/1% low FPS **44.11/10.69→56.78/26.46**, with P99 **89.78→33.17 ms**. The separate GPU pair (`world-horse-gpu-vacancy1b-152438.json`) reduces `voxel_update` mean/P95/max **12.07/45.94/85.40→9.21/13.12/31.24 ms**. The offscreen horse (`world-horse-offscreen-152729.json`) darkens 1,206/1,800 floor samples versus a no-caster control; observed removal (`world-horse-vacancy1b-quality-152816.json`) leaves no extra retained body cells in either build. The earlier settled-image comparison had different animation/cache inputs. The final frozen 1b control (`world-horse-frozen-parity-154623.json`) now gives zero RGB, body-cell and word differences, with matching matrices/maps/LOD2. These results support the accepted preview under the scope above, not 144 FPS or 128-source performance. Hidden edits, four-plane/mask capacity and retained history inside occupied cells remain limitations.

**Rejected candidate 2:** the extra coarse bound passed frozen parity (`world-horse-frozen-parity-154221.json`), but its frame-rate benefit was inconclusive, including a regression and an invalid minimized reverse run. It is not part of WorldEntities1; the single-level 1b path is retained.

### Historical mode 2 profiling: EntityScreen4

Earlier actual-world runs 132350 (`horse-user-perf-132350.json`), 132850 (`horse-user-perf-132850.json`), and first HUD runs are **scene-only**: the horse wandered, invalidating their named near/inside positions. 134147 (`horse-hud-fixed-134147.json`) fixed the horse position, but `select_pack` → `configure` reset the requested 32/32 to **8/5 and native blob OFF**; bob was subsequently re-enabled.

The corrected horizontal comparison (`horse-exact-horizontal-135040.json`) uses the owned saved-world copy, frozen horse, 12 unchanged lights, **vanilla 26.3, 1920×1080, verified 32/32, native blob/bob/Improved Transparency ON**. Each pose uses 2 seconds warmup and 5 seconds measurement. Mode `0` disables Chroma entity casting while preserving world-shadow reception and light:

| Pose | Mode 2 average FPS | Mode 0 average FPS |
| --- | ---: | ---: |
| Standing beside lamp | 113.31 | 119.80 |
| Crouched beside lamp | 70.05 | 72.73 |
| Inside horizontal view | 91.56 | 109.92 |

GPU timestamps (`horse-gpu-exact-135632.json`) separate the cost: standing→crouching raises Mode 2 `shade` **3.314→7.016 ms**, while `voxel_update` stays **3.156→3.121 ms**. Mode 0 crouched `shade` is still **6.720 ms**. The alpha capture (`horse-horizontal-alpha-135312.json`) confirms 2,073,472 tagged, brightened entity pixels; only 128 service pixels carry depth 1.

A diagnostic bypass of **world-shadow reception on tagged entities** reduces `shade` **6.933→1.644 ms** in a separate GPU pair (`horse-gpu-bypass-140032.json`), and average FPS **64.01→135.94** in the frame-time pair (`horse-receive-bypass-135906.json`). This identifies the dominant incremental work in this **mode 2** view, not the cost of moving world entity casters. The bypass removes receiving shadows and is **not a quality-preserving fix**.

The nine-depth exact-address cache preserved bit-identical settled RGB and inputs (`horse-parity-141332.json`), but worsened FPS 72.24→58.67 (`horse-depth-reuse-fps-141441.json`) and GPU `shade` 6.523→8.976 ms (`horse-gpu-depth-reuse-141552.json`). It was **rejected and reverted**; its cause of regression is not established by these timings.

**Historical EntityScreen4 / mode 2: empty-region proof.** At most 16 reads of the existing packed occupancy LOD2 test a conservative box containing the receiver, full area source and normal bias. An empty box inside the cache window skips the world filter; occupied, oversized or out-of-window boxes keep the existing hybrid PCSS path. The embedded-source guard remains. This is a proof relative to the observed cache, not access to unseen geometry; it preserves screen casters and receiving shadows. Auto and Static are unchanged.

The fresh warmed near-horse pair (`horse-empty-region-fps-142657.json`) used the copied user scene with 12 original lamps, frozen horse, vanilla 26.3/OpenGL, RTX 4060 Ti 16 GB, 1920×1080, verified 32/32 and native blob/bob/Improved Transparency ON; 2 seconds warmup + 5 seconds measured:

| Metric | EntityScreen3 | EntityScreen4 / EmptyRegion |
| --- | ---: | ---: |
| Average FPS | 69.97 | **125.70** |
| 1% low FPS | 39.03 | **53.17** |
| Median frame time, ms | 12.3689 | **6.9147** |
| P99 frame time, ms | 25.5385 | **18.6133** |

The separate GPU pair (`horse-gpu-empty-region-142814.json`) reduced `shade` **7.774→1.968 ms**, with no dropped queries and the profiler detached afterwards. The near view is RGB bit-identical (`horse-parity-142523.json`). In the wider view, CPU reconstruction (`horse-empty-region-wide-analysis.json`) independently confirms empty LOD2 boxes for lamp 7 at all 470 changed entity pixels: old PCSS samples hit the floor outside the physical light-path box. The remaining changed pixel has a one-byte pre-colour drift. This explains this capture's difference; it is not universal visual equivalence.

The closed-wall comparison (`horse-empty-wall-143003-comparison.json`) is bit-identical on the horse with the lamp ON and OFF. Both builds retain the same 75 of 8,169 positive-control pixels above a three-byte residual, maximum 7; absolute zero light leakage is **not** established. The moving-flashlight control (`horse-empty-flashlight-143221.json`) passes 116 medium + 125 narrow samples: no camera/source drops, empty emitter cells, no zero maps and constant decoded intensity during native walking/turning with bob. This verifies transport and following, not all-pixel temporal smoothness. The three-position wall control (`horse-empty-transition-143637.json`) matches horse RGB exactly with the source blocked and fully clear. At the boundary, 775 pixels differ (−40 to +7): native horse colour/depth and source metadata match, but cache inputs differ (`horse-empty-transition-143637-data.json`) by 56 LOD2 words and 646 map texels/atlas records. The boundary comparison is therefore **inconclusive as a shader-only A/B**; it does not establish smoothness through every transition.

All these pairs ran while the user's Minecraft **PID 43724** remained active. They are scoped comparative diagnostics with shared GPU load, not isolated/general FPS guarantees. GPU timings are instrumented and separate from normal frame-time runs. **These mode 2 runs did not reproduce or fix the user's original world-caster stall. The later mode 1 diagnosis is above. EntityScreen4 does not guarantee 144 FPS; this revision has no new 128-source load test.**

## Русский

### Что изменилось в 26.3

Официальные примечания описывают новый OIT, MultiDrawIndirect для блоков, ShaderC на обоих графических бэкендах, явные locations шейдеров и постоянно включённый `minecraft:end_of_frame`. Добавлен также `integrate_depth` для глубины HUD/гизмосов. Это изменения рендеринга, а не заявленный API камеры источника света или геометрии сущностей для RP. [Официальные примечания 26.3](https://feedback.minecraft.net/hc/en-us/articles/48913133328013-Minecraft-Java-Edition-26-3).

### Что действительно доступно ресурспаку

* **Цвет и глубина текущего основного кадра.** `GameRenderer` загружает конечные эффекты с `MAIN_TARGETS`, где есть только `minecraft:main`. `LevelTargetBundle.get/replace` знают `main` и `entity_outline`, но второй передаётся отдельному эффекту обводки. Произвольный внешний буфер не проходит проверку `PostChain.load`. Код framegraph (`horse-engine/research-framegraph.javap.txt`).
* **Собственные промежуточные цели и post-проходы.** `PostChainConfig.Pass` задаёт вершинный/фрагментный шейдер, текстуры, блоки uniform и один выход. `PostPass` рисует полноэкранный треугольник в одну цветовую цель. Внутренние цели используют RGBA8 и стандартную глубину, могут иметь фиксированный размер или размер кадра и сохраняться между кадрами. JSON не предоставляет compute, storage buffers, несколько цветовых выходов или повторную отрисовку модели из позиции лампы. Возможности графического бэкенда сами по себе не создают таких привязок для RP. Post API (`horse-engine/research-post-api.javap.txt`).
* **Штатные входы core-шейдеров.** Есть вершины, цвет, нормаль, координаты текстуры/освещения/наложения, матрицы и параметры камеры. Нет семантического ID моба, скелета или всей модели. `ModelFeatureRenderer.prepareModel` применяет анимацию и передаёт вершины через CPU-вызов `Model.renderToBuffer`. Путь модели (`horse-engine/research-horse.javap.txt`), uniform и шейдеры (`horse-engine/research-shader-contracts.txt`).

Внутренние OIT-ресурсы `depth_bounds`, `depth_bounds_culled`, transmittance, accumulate, глубина облаков и terrain действительно существуют. Однако они не открыты произвольному post JSON. В них хранятся границы прозрачной глубины, суммарное пропускание и цвет текущего ракурса, а не отдельные модели сущностей. Доступ core-шейдера к своим штатным OIT-входам не означает доступ нового post-прохода к ним. Framegraph (`horse-engine/research-framegraph.javap.txt`), выходы OIT (`horse-engine/research-shader-contracts.txt`).

### Дополнительный проход glowing: возможность с условиями

Дополнительная геометрия действительно есть. В 26.3 класса `OutlineBufferSource` уже нет: `SubmitNodeCollection.submitModel` сначала отправляет обычную модель, затем ту же анимированную модель/состояние/позу в outline-фазу, если цвет контура ненулевой и материал поддерживает контур. У `rendertype_outline` есть позиция, UV и цвет, штатные матрицы/глобальные данные и текстура сущности; каталога ламп Chroma среди привязок нет. Байткод и штатные шейдеры (`horse-engine/research-outline.javap.txt`).

* **Нужно состояние glowing.** `Minecraft.shouldEntityAppearGlowing` проверяет свечение; исключение — контуры игроков по клавише наблюдателя. Ресурспак не устанавливает этот флаг обычным мобам. Автоматическое включение требует команды/датапака/мода на стороне игры: это явная дополнительная зависимость. Нужны также игрок и непанорамный режим камеры. Проверки дистанции, frustum и видимости секции выполняются до отправки геометрии.
* **Передача в основной кадр возможна.** Отдельный outline post получает оба внешних буфера: `minecraft:main` и `minecraft:entity_outline`. Он может обработать данные своими проходами и записать их в зарезервированную область main до end-of-frame. Потребуется согласовать последующее штатное смешивание контура, защиту области передачи и кадры без outlined-сущностей. Такой прототип здесь не реализован и не проверен.
* **Готовой карты глубины источника нет.** `executeOutline` очищает и рисует только цвет, **без depth attachment**, с обычной записью цвета без смешивания. Перенос вершин в ракурс лампы и запись `gl_FragDepth` не выберут ближайшие поверхности пересекающихся треугольников. RP не меняет эти привязки и blend state. Упаковка модели в отдельные пиксельные записи с дальнейшим вычислением видимости теоретически возможна, но требует нового транспорта, ёмкости и замеров стоимости.
* **Индексы не являются ID моба.** Indexed draw использует одну instance и `baseVertex = vertexOffset / vertexStride`. Индекс вершины адресует геометрию кадра; стабильного ID сущности/модели между кадрами нет. Номер примитива сам по себе не различает модели между draw-вызовами. В batch могут попасть несколько моделей, слоёв и материалов; предположения об адресах нужно подтверждать захватом draw. GPU-проверки этого транспорта не было.

Так можно исследовать получение анимированной геометрии **отправленных на отрисовку, явно glowing** сущностей, в том числе скрытой обычной глубиной сцены, сохраняя нормальную отрисовку тела. Это не даёт мобов за пределами frustum, бесплатную shadow map или незаметную замену самостоятельному RP.

### Лошадь и установленные моды

| Поверхность | Проверенный путь | Значение для Chroma |
| --- | --- | --- |
| Обычное тело | `EntityModel` → `entityCutout` → `core/entity` | Непрозрачная запись без смешивания; прошедший фрагмент получает метку сущности. |
| Броня и седло | Equipment-слои `HorseRenderer` → `EquipmentLayerRenderer` → `armorCutoutNoCull/Glint` | То же семейство entity-шейдеров; отдельного обходящего метку шейдера лошади не найдено. |
| Отметины шерсти | `HorseMarkingLayer.submit` → `entityTranslucent` | При Improved Transparency ON используется OIT; действующая маска считает занятые пиксели неизвестными. |
| Круглое штатное пятно | `ShadowFeatureRenderer` → `entityShadow` → `core/rendertype_entity_shadow` | Отдельный прозрачный/OIT-проход. Это построенные CPU квадраты на земле с радиусом/UV/alpha, а не силуэт тела. У обычного blob pipeline запись глубины выключена. |

Подтверждение: лошадь (`horse-engine/research-horse.javap.txt`), pipeline (`horse-engine/research-pipelines.javap.txt`), пятно тени (`horse-engine/research-blob.javap.txt`). Действующая OIT-маска может исключать из Chroma и пиксели пола под штатным пятном. Это ограничение изображения для проверки, а не доказанная причина просадки.

Проверены **Sodium 0.9.3-alpha.1**, **EMF 3.3.8**, **ETF 7.2.4** для 26.3. У Sodium быстрый путь сущностей передаёт исходный цвет вершин, а mixin теней ускоряет те же квадраты на земле. Собственные шейдеры и прямые изменения pipeline относятся к terrain; `entity.fsh` не входит в список неподдерживаемых замен. В проверенном living-renderer EMF меняются модель, анимация и текстуры. Прямой замены entity blend state в проверенных путях не обнаружено; это статический аудит, а не гарантия совместимости всех настроек. Выдержки модов (`horse-engine/research-mods.javap.txt`), хеши и скан (`horse-engine/research-manifest.json`).

ETF способен добавлять светящиеся наложения через `entityTranslucent`, а в режиме BRIGHT — через `beaconBeam(texture, true)`. Поэтому конкретный нестандартный ресурспак моделей/текстур может использовать дополнительные проходы. Их активность и наличие метки нужно подтверждать захватом реальной отрисовки.

### Практические варианты

| Вариант | Возможная польза | Ограничение / состояние |
| --- | --- | --- |
| Текущий ограниченный экранный луч | Контактные тени видимых частей сущности без истории движущейся модели | Только доступная экранная глубина; раздельный замер стоимости сцены с лошадью приведён ниже. |
| Перспективно-корректный экранный DDA | Избежать повторов/пропусков пикселей при равномерном шаге в мировом пространстве | Нужны ограниченный обход и проверка штатной обратной глубины; это пока не исправление установленной причины. |
| Консервативная иерархия присутствия сущностей/глубины | Пропуск областей без подходящего препятствия | Реализуема post-проходами, но требует разработки и замера; скрытые поверхности не восстанавливает. |
| Контактный результат меньшего разрешения с восстановлением по глубине | Меньше повторной работы на пиксель | Дополнительные проходы и погрешности краёв/тонких деталей; здесь не реализован и не проверен. |
| Кеш увиденной мировой геометрии | Сохраняет ранее наблюдавшиеся препятствия вне кадра | История движущихся тел, цена сбора и конечная вместимость; возврат мобов в кеш не является доказанным исправлением. |
| Штатное круглое пятно | Недорогой приблизительный контакт с землёй | Не повторяет силуэт и не даёт тень от произвольной лампы на стене. |
| Расширение рендерера или явно переданная proxy-геометрия | Реальные данные сущностей или проход из позиции света | Выходит за штатный RP API; упрощённые proxy сохраняют свои погрешности. |

Первоисточники подтверждают методы, но не диагноз этой сцены. Работа McGuire и Mara [Efficient GPU Screen-Space Ray Tracing](https://jcgt.org/published/0003/04/04/paper.pdf) описывает перспективно-корректный DDA с последовательными экранными выборками вместо равномерных 3D-шагов. [AMD FidelityFX SSSR](https://gpuopen.com/fidelityfx-sssr/) показывает иерархический обход глубины. Готовый SDK использует HLSL wave-операции и собственную GPU/compute-интеграцию: его нельзя просто добавить в vanilla RP. Адаптация Chroma потребует доступных фрагментных проходов и отдельной проверки точности и скорости.

В текущем [shade.fsh](../assets/chroma/shaders/post/shade.fsh) помеченная поверхность сущности пропускает `chromaEntityShadow`, но по-прежнему рассчитывает мировой `chromaShadow`. Поэтому увеличение правильно помеченного тела в кадре само по себе не увеличивает число контактных экранных лучей на нём. Сначала следует отделить потерю метки/дополнительные слои от мирового фильтра и работы постоянного кеша.

### Исправленный диагноз: движущаяся сущность в мировом режиме 1

Пользователю нужны мировые тени сущностей, а не экранные. Новый замер кадров (`world-horse-mode1-moving-fps-150331.json`) явно использует режим `1`, одну исходную неподвижную лампу и сохранённую лошадь в броне. Исходный мировой режим при движении даёт **41,81 FPS / 10,15 FPS 1% low / 91,79 мс P99**; EmptyRegion — **44,33 / 9,44 / 96,90 мс**, то есть просадку не устраняет.

Отдельный GPU-профиль (`world-horse-gpu-mode1-150543.json`) локализует всплески в обновлении геометрии:

| Мировой режим 1 | `voxel_update`: среднее / P95 / максимум, мс | `shade`: среднее, мс |
| --- | ---: | ---: |
| Исходный, неподвижная лошадь | 6,59 / 10,18 / 13,53 | 6,59 |
| Исходный, движущаяся лошадь | **13,32 / 53,60 / 108,54** | 6,27 |
| EmptyRegion, движущаяся лошадь | 14,23 / 70,44 / 86,98 | 6,50 |

Условия: vanilla 26.3, 1920×1080, подтверждённые 32/32, штатные тени сущностей/покачивание/Improved Transparency ON; основной PID 43724 работал параллельно. Управляемое штатное движение — смещение ±0,12 блока и поворот ±25°; столкновение могло отодвигать игрока, камера не была жёстко зафиксирована. Замеры кадров и GPU выполнялись отдельно. Принятый вариант 1b использует одну сводку глубины текущего кадра `256 × 256` для ускорения точных доказательств пустоты, сохраняя режим `1` **без экранного луча тени**. Сомнительные тайлы сохраняют точные штатные пиксельные проверки; удаления истории по таймеру нет.

**Принятый WorldEntities1 / VacancyBounds1b:** свежая пара с движением в режиме 1 (`world-horse-vacancy1b-moving-fps-152250.json`) улучшает средний/1% low FPS **44,11/10,69→56,78/26,46**, P99 — **89,78→33,17 мс**. Отдельная GPU-пара (`world-horse-gpu-vacancy1b-152438.json`) снижает среднее/P95/максимум `voxel_update` **12,07/45,94/85,40→9,21/13,12/31,24 мс**. Лошадь вне кадра (`world-horse-offscreen-152729.json`) затемняет 1 206/1 800 проб пола относительно контроля без отбрасывания теней; после наблюдаемого удаления (`world-horse-vacancy1b-quality-152816.json`) ни у одной сборки нет лишних сохранённых ячеек тела. Прежнее сравнение установившихся кадров имело разные входы анимации/кеша. Итоговый замороженный контроль 1b (`world-horse-frozen-parity-154623.json`) даёт ноль различий RGB, ячеек и слов тела при совпадающих матрицах/картах/LOD2. Эти результаты подтверждают принятую предварительную сборку в условиях выше, а не 144 FPS или скорость 128 источников. Скрытые изменения, ёмкость четырёх плоскостей/масок и история внутри занятых ячеек остаются ограничениями.

**Отклонённый кандидат 2:** дополнительная крупная сводка прошла замороженное сравнение (`world-horse-frozen-parity-154221.json`), но выигрыш по FPS не подтверждён: был регресс, обратный прогон со свёрнутым окном недопустим. Этот вариант не входит в WorldEntities1; сохранён одноуровневый 1b.

### Прежнее профилирование режима 2: EntityScreen4

Ранние замеры реального мира 132350 (`horse-user-perf-132350.json`), 132850 (`horse-user-perf-132850.json`) и первые проходы с HUD описывают **только сцену**: лошадь ушла, поэтому названия позиций «рядом/внутри» недостоверны. В 134147 (`horse-hud-fixed-134147.json`) положение лошади исправлено, но `select_pack` → `configure` сбросил запрошенные 32/32 до **8/5 и штатного пятна OFF**; bob затем включили снова.

Исправленное горизонтальное сравнение (`horse-exact-horizontal-135040.json`) использует тестовую копию сохранённого мира, замороженную лошадь, 12 неизменённых ламп, **vanilla 26.3, 1920×1080, подтверждённые 32/32, штатное пятно/bob/Improved Transparency ON**. На позу — 2 секунды прогрева и 5 секунд измерения. Режим `0` отключает отбрасывание теней Chroma сущностями, сохраняя получение мировых теней и света:

| Положение | Средний FPS, режим 2 | Средний FPS, режим 0 |
| --- | ---: | ---: |
| Стоя со стороны лампы | 113,31 | 119,80 |
| Вприсядку со стороны лампы | 70,05 | 72,73 |
| Внутри, горизонтальный взгляд | 91,56 | 109,92 |

GPU timestamps (`horse-gpu-exact-135632.json`) разделяют стоимость: при приседании `shade` в режиме 2 растёт **3,314→7,016 мс**, а `voxel_update` остаётся **3,156→3,121 мс**. В режиме 0 присевший вид всё ещё тратит на `shade` **6,720 мс**. Захват alpha (`horse-horizontal-alpha-135312.json`) подтверждает 2 073 472 помеченных и осветлённых пикселя сущности; глубина 1 есть только у 128 служебных пикселей.

Диагностический пропуск **получения мировых теней помеченными сущностями** снижает `shade` **6,933→1,644 мс** в отдельной GPU-паре (`horse-gpu-bypass-140032.json`), а средний FPS **64,01→135,94** в паре измерений кадров (`horse-receive-bypass-135906.json`). Так установлена основная дополнительная работа в этом ракурсе **режима 2**, а не стоимость движущихся сущностей как мировых препятствий. Пропуск убирает получение теней и **не является исправлением с сохранением качества**.

Кеш девяти глубин по точному адресу сохранил побитовое совпадение RGB и входов после стабилизации камеры (`horse-parity-141332.json`), но ухудшил FPS 72,24→58,67 (`horse-depth-reuse-fps-141441.json`) и GPU `shade` 6,523→8,976 мс (`horse-gpu-depth-reuse-141552.json`). Кандидат **отклонён и отменён**; причина ухудшения по этим замерам не установлена.

**Прежний EntityScreen4 / режим 2: проверка пустой области.** Не более 16 чтений существующего упакованного LOD2 проверяют прямоугольную область, охватывающую приёмник, весь площадной источник и смещение по нормали. Пустая область внутри окна кеша позволяет пропустить мировой фильтр; занятая, слишком большая или выходящая за окно сохраняет прежний гибридный PCSS. Защита источника внутри препятствия остаётся. Это проверка по увиденной геометрии кеша, а не доступ к невиденной геометрии; отбрасывание экранных теней и получение мировых сохранены. Auto и Static не изменены.

Свежая прогретая пара у лошади (`horse-empty-region-fps-142657.json`): копия пользовательской сцены с 12 исходными лампами, неподвижная лошадь, vanilla 26.3/OpenGL, RTX 4060 Ti 16 ГБ, 1920×1080, подтверждённые 32/32, штатные тени сущностей/покачивание/Improved Transparency ON; 2 секунды прогрева + 5 секунд замера:

| Показатель | EntityScreen3 | EntityScreen4 / EmptyRegion |
| --- | ---: | ---: |
| Средний FPS | 69,97 | **125,70** |
| 1% low FPS | 39,03 | **53,17** |
| Медиана времени кадра, мс | 12,3689 | **6,9147** |
| P99 времени кадра, мс | 25,5385 | **18,6133** |

Отдельная GPU-пара (`horse-gpu-empty-region-142814.json`) снизила `shade` **7,774→1,968 мс**, без потерянных запросов; после замера профилировщик отключён. RGB ближнего вида совпадает побитово (`horse-parity-142523.json`). В общем ракурсе CPU-восстановление (`horse-empty-region-wide-analysis.json`) независимо подтверждает пустые области LOD2 для лампы 7 во всех 470 изменившихся пикселях сущностей: старые пробы PCSS попадали в пол вне области физических путей света. У оставшегося изменившегося пикселя есть сдвиг исходного цвета на один байт. Это объяснение конкретного захвата, а не универсальная визуальная эквивалентность.

Сравнение за закрытой стеной (`horse-empty-wall-143003-comparison.json`) даёт побитовое совпадение лошади при включённой и выключенной лампе. Обе сборки сохраняют одинаковые 75 из 8 169 пикселей положительного контроля с остатком больше трёх байт, максимум 7; абсолютное отсутствие просачивания света **не подтверждено**. Движущийся фонарик (`horse-empty-flashlight-143221.json`) проходит 116 проб среднего + 125 узкого луча: без пропадания пакетов камеры/источника, с пустыми ячейками лампы, ненулевыми картами и постоянной интенсивностью при штатной ходьбе/поворотах с покачиванием. Это проверка передачи данных и следования, а не плавности каждого пикселя. Контроль трёх позиций у стены (`horse-empty-transition-143637.json`) даёт точное совпадение RGB лошади при перекрытом и полностью открытом пути. На границе отличаются 775 пикселей (от −40 до +7): штатные цвет/глубина лошади и метаданные источника совпадают, но входы кеша различаются (`horse-empty-transition-143637-data.json`) на 56 слов LOD2 и 646 текселей карты/записей атласа. Поэтому пограничный результат **неокончательный для сравнения только шейдера** и не подтверждает плавность каждого перехода.

Во всех парах параллельно работал пользовательский Minecraft **PID 43724**. Это сравнительная диагностика конкретной сцены при общей нагрузке на GPU, а не изолированная гарантия FPS. GPU-профиль инструментирован и выполнялся отдельно от обычных измерений кадров. **Эти прогоны режима 2 не воспроизвели и не исправили исходную просадку мировых теней пользователя. Более поздний диагноз режима 1 приведён выше. EntityScreen4 не гарантирует 144 FPS; нового нагрузочного теста 128 источников для этой правки нет.**


### Earlier screen-ray controls / Прежние проверки экранного луча

EntityScreen2/3 are historical screen-mode experiments. EntityScreen2 removed the broad comb gaps at six recorded points and retained identical cow RGB between modes 0/2 over 25,485 tagged body pixels. EntityScreen3 preserved 300,835 floor and 25,485 cow samples after projection/catalog optimizations. Its isolated 8/5 one-lamp comparisons reached 110.57 FPS inside a cow and 136.88 during a zombie walk; those results do not establish world-entity-caster performance. Evidence: `entityscreen2-124230.json`, `entity-screen2-comb-regression.json`, `entity-screen3-parity.json`, `entity-screen-perf-125640.json`, `entity-screen-perf-125732.json` under `audit/shadows/`.

EntityScreen2/3 — прежние эксперименты экранного режима. EntityScreen2 убрал широкие полосы в шести сохранённых точках и сохранил одинаковый RGB коровы в режимах 0/2 на 25 485 помеченных пикселях тела. EntityScreen3 после оптимизации проекции/каталога сохранил 300 835 проб пола и 25 485 проб коровы. Его изолированные сравнения при 8/5 и одной лампе дали 110,57 FPS внутри коровы и 136,88 при проходе через зомби; они не подтверждают скорость мировых теней сущностей. Отчёты: `entityscreen2-124230.json`, `entity-screen2-comb-regression.json`, `entity-screen3-parity.json`, `entity-screen-perf-125640.json`, `entity-screen-perf-125732.json` в `audit/shadows/`.
