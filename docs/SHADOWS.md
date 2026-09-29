# Chroma Shadows / Тени Chroma

**Dynamic and Static for Minecraft Java 26.3; Auto remains the main shadow-free edition. / Dynamic и Static для Minecraft Java 26.3; основной вариант Auto сохранён без теней.**

| Edition / Вариант | Archive / Архив | Geometry / Геометрия |
| --- | --- | --- |
| Auto — main / основной | `Chroma-Auto-26.3.zip` | No shadows / Без теней |
| Shadows Dynamic | `Chroma-Shadows-Dynamic-26.3.zip` | Observed-world cache / Кеш увиденной геометрии |
| Shadows Static — objCubed | `Chroma-Shadows-Static-objCubed-26.3.zip` | Export of this world / Экспорт этого мира |

## English

Enable **only one edition**, at highest resource-pack priority. Press **F3+T** after replacing it and after changing worlds or dimensions. Static must match its exported world and dimension; this reload does not update its baked geometry. Light commands remain the same: up to 128 sources, one `item_display` each, five reusable shapes, independent colour/brightness/radius/direction, no assigned source ID. Both shadow editions allow moving lights. See the [light commands](README.en.md).

**Dynamic** records visible depth into a persistent, world-coordinate voxel grid: `256³` quarter-block cells cover a moving `64³`-block window. Previously observed blockers can remain effective outside the current view, while they stay inside that window. It cannot know geometry that has never been seen, changes behind the camera, or hidden surfaces that depth never exposed. Observed geometry updates in eight phases; source maps refresh within eight frames, giving roughly 16 rendered frames for an observed edit to propagate. This is a frame budget, not a wall-clock guarantee. Removing all lamps preserves the geometry cache. **F3+T** clears the history; use it after a world or dimension change.

**Static** reads exported block geometry directly. A blocker inside the exported bounds is available from the first frame, even behind the camera. Blocks and doors retain their saved state until re-exported; moving lights do not require re-export. The export uses native 26.3 occlusion/collision shapes on a quarter-block grid, including saved door orientations. Glass, water and leaves are excluded. Moving entities, custom resource-pack model geometry and texture cutout holes are not exported. Thin details may thicken to a quarter block. Inspect `docs/shadow-world.json` inside the Static ZIP for bounds and export limitations.

**Shadow calculation:** each source has a cached `128 × 128` octahedral map of distances to blockers, anchored to its world position. A PCSS-like blocker search and filter make the shadow edge softer with blocker/receiver separation. `CHROMA_SOURCE_SIZE` in `assets/chroma/shaders/include/shadow_config.glsl` controls the emitter radius; default `0.35` blocks. Rebuild/reload after editing it. This is source-based occlusion, without screen-space shadow ray marching or frame-dependent noise; Dynamic's *geometry acquisition* still depends on what was observed. Finite map/voxel resolution can produce edge aliasing or thin-detail errors.

**What is shadowed:** direct light on world surfaces. The existing weak analytic glow remains unshadowed, so it can bleed through blockers. Set `VOL_STRENGTH` to `0.0` in `assets/chroma/shaders/post/shade.fsh` and rebuild/reload to disable it. First-person hands/held items and the separate 3D-HUD retain vanilla colour: only their actual covered pixels are excluded from Chroma light/fog/shadows and from voxel observations, so they do not become world occluders. World pixels around them are still processed; no fixed screen rectangle is masked. The ordinary 2D GUI is unchanged.

Playing requires only the RP and vanilla commands: no extra Java helper, mod or required datapack. Exporting Static is an authoring step using Python with NumPy, Pillow and nbtlib, plus the installed Minecraft 26.3 Java/runtime libraries. Save and close the world before exporting. Use the shared commands below from the project directory; optional `--min X Y Z --max X Y Z` limits the export, with maximum bounds exclusive.

## Русский

Включите **только один вариант** с наивысшим приоритетом. Нажмите **F3+T** после замены пака и после перехода в другой мир или измерение. Static должен соответствовать экспортированному миру и измерению; перечитывание пака само по себе не обновляет геометрию. Команды света прежние: до 128 источников, один `item_display` на источник, пять повторяемых форм, независимые цвет/яркость/радиус/направление, без назначения ID. Свет можно перемещать в обоих вариантах. См. [команды источников](README.ru.md).

**Dynamic** собирает видимую глубину в постоянный кеш с координатами мира: `256³` ячеек по четверти блока покрывают перемещаемое окно `64³` блока. Увиденные препятствия могут продолжать отбрасывать тени вне экрана, пока находятся в этом окне. Геометрия, которую камера ещё не видела, изменения за камерой и скрытые поверхности ему неизвестны. Геометрия обновляется за восемь фаз, карты источников — в пределах восьми кадров: увиденное изменение обычно проходит оба этапа примерно за 16 отрисованных кадров. Это число кадров, а не гарантия времени в секундах. Удаление всех ламп сохраняет кеш геометрии. **F3+T** очищает историю; используйте его после смены мира или измерения.

**Static** читает экспортированную геометрию блоков. Препятствия внутри границ экспорта доступны с первого кадра, включая объекты за камерой. Блоки и двери сохраняют записанное состояние до нового экспорта; для перемещения ламп экспорт не нужен. Используются штатные формы перекрытия/столкновения 26.3 на сетке в четверть блока, включая сохранённую ориентацию дверей. Стекло, вода и листва исключены. Движущиеся сущности, геометрия нестандартных моделей RP и отверстия в текстурах не экспортируются. Тонкие детали могут утолщаться до четверти блока. Границы и ограничения конкретного экспорта находятся в `docs/shadow-world.json` внутри Static ZIP.

**Расчёт теней:** у каждого источника есть кешируемая октаэдрическая карта `128 × 128` с расстояниями до препятствий, привязанная к его позиции в мире. Поиск перекрывающих объектов и фильтрация по принципу PCSS расширяют полутень при удалении поверхности от препятствия. `CHROMA_SOURCE_SIZE` в `assets/chroma/shaders/include/shadow_config.glsl` задаёт радиус излучателя, по умолчанию `0.35` блока. После изменения пересоберите и перечитайте пак. Проверка идёт от источника, без трассировки теней по экранной глубине и шума, меняющегося от кадра к кадру; при этом *сбор геометрии* Dynamic зависит от увиденного. Конечное разрешение карт и вокселей ограничивает точность краёв и тонких деталей.

**Что затеняется:** прямое освещение поверхностей мира. Прежнее слабое аналитическое свечение не затеняется и может проходить сквозь препятствия. Для его отключения задайте `VOL_STRENGTH` равным `0.0` в `assets/chroma/shaders/post/shade.fsh` и пересоберите/перечитайте пак. Руки/предметы от первого лица и отдельный 3D-HUD сохраняют обычный цвет: только занятые ими пиксели исключаются из света/тумана/теней Chroma и наблюдений воксельного кеша, поэтому они не становятся препятствиями мира. Окружающие пиксели мира продолжают обрабатываться; фиксированная область экрана не маскируется. Обычный двумерный интерфейс не меняется.

Для игры нужны только RP и обычные команды; дополнительные Java-модули, моды и обязательный датапак не нужны. Экспорт Static выполняется при подготовке пака через Python с NumPy, Pillow и nbtlib, а также установленную Java с библиотеками Minecraft 26.3. Перед экспортом сохраните и закройте мир. Команды ниже выполняются из папки проекта. Необязательные `--min X Y Z --max X Y Z` ограничивают область; верхняя граница не включается.

## Build / Сборка

```powershell
python tools/build_shadows.py --output "dist/Chroma-Shadows-Dynamic-26.3.zip"

python tools/export_shadow_world.py --world "C:\Users\konst\AppData\Roaming\PrismLauncher\instances\26.3\minecraft\saves\objCubed" --output "audit/shadows/export-objCubed"
python tools/build_shadows.py --static-volume "audit/shadows/export-objCubed" --output "dist/Chroma-Shadows-Static-objCubed-26.3.zip"
```

Copy the chosen ZIP to `minecraft/resourcepacks`; other players need the same Static export. / Скопируйте выбранный ZIP в `minecraft/resourcepacks`; другим игрокам нужен тот же экспорт Static.

## Evidence and reference / Проверки и источник

[Auto validation](VALIDATION.md) covers the main 128-source build and historical 32-source tests. See [shadow validation](SHADOW_VALIDATION.md) for the separate functional checks and measured performance under stated scene conditions. Auto timings are not shadow-performance evidence, and fixture FPS is not a promise for every world. / [Проверки Auto](VALIDATION.md) включают основную сборку на 128 источников и прежние тесты 32 источников. Отдельные функциональные проверки и измерения производительности с условиями сцены — в [отчёте по теням](SHADOW_VALIDATION.md). Замеры Auto не подтверждают производительность теней, а FPS тестовой сцены не гарантируется в каждом мире.

Research reference: [JNNGL/VanillaDI](https://github.com/JNNGL/VanillaDI). Its README documents reprojection artifacts when its control marker moves. Chroma uses native camera/world coordinates for its cache; this does not remove Dynamic's observed-depth coverage limit. / Источник для исследования: [JNNGL/VanillaDI](https://github.com/JNNGL/VanillaDI). В README отмечены артефакты перепроецирования при перемещении управляющего маркера. Chroma использует штатные координаты камеры и мира, но это не устраняет ограничение Dynamic на геометрию, доступную из наблюдаемой глубины.
