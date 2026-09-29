# Chroma — 128 automatic coloured lights

A standalone resource pack for **Minecraft Java 26.3** (resource-pack format **97.1**). Up to **128 simultaneously rendered light sources** are collected automatically. Reuse the same five light models with independent colours, radii, brightness and directions: no manually assigned slots, one entity per light, no required mod or datapack.

**Chroma Auto remains the main, shadow-free release.** This branch adds two shadow editions: **Dynamic** collects observed geometry into a world-coordinate voxel cache; **Static** uses exported geometry from a particular saved world. Both allow moving lights and soften shadows according to the source and blocker positions. See the [bilingual shadow guide](docs/SHADOWS.md) for coverage limits and setup, and [shadow validation](docs/SHADOW_VALIDATION.md) for tests and benchmark conditions.

- [English guide](docs/README.en.md)
- [Инструкция на русском](docs/README.ru.md)
- [Shadows / Тени: Dynamic and Static](docs/SHADOWS.md)
- [Commands / Команды](docs/examples.mcfunction)
- [128-light example / Пример с 128 источниками](docs/examples-128.mcfunction)
- [Auto validation / Проверки Auto](docs/VALIDATION.md)
- [Shadow validation / Проверки теней](docs/SHADOW_VALIDATION.md)
- [Credits](CREDITS.md)

Place the chosen pack in `minecraft/resourcepacks`, enable only one Chroma edition at highest priority, and press **F3+T** after replacing files. For shadow editions, also reload after switching worlds or dimensions to reset cached geometry. Lights use the same vanilla `item_display` summon commands in all editions. The resource pack does not create entities itself. The 128-source rendering budget is finite. In `objCubed`, the optional test datapack provides `/reload`, then `/function chroma_test:spawn128`; cleanup is `/function chroma_test:clear128`.

**Основная версия Auto сохранена без теней.** В этой ветке доступны Dynamic с кешем увиденной геометрии и Static с экспортом конкретного мира. Включайте только один вариант Chroma. Ограничения и инструкции на обоих языках: [SHADOWS.md](docs/SHADOWS.md); результаты и условия измерений: [проверки теней](docs/SHADOW_VALIDATION.md).

Shadows affect direct surface light. The weak analytic glow remains unshadowed and can bleed through blockers; hands and HUD retain vanilla lighting. Dynamic's geometry cache survives removal of all lights; **F3+T** resets it. / Тени действуют на прямое освещение поверхностей. Слабое аналитическое свечение не затеняется и может проходить сквозь препятствия; руки и HUD сохраняют обычное освещение. Кеш геометрии Dynamic сохраняется при удалении всех ламп; **F3+T** сбрасывает его.

![Static source shadows in Minecraft 26.3 / Тени от источников в Minecraft 26.3](docs/images/chroma-shadows-static-live.png)
