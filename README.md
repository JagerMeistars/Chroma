# Chroma

**Coloured lights and world-space shadows for Minecraft Java 26.3.**
A vanilla resource pack with up to **128 simultaneous lights**, five light shapes, and independent colour, brightness, range and direction. No required mods or datapacks. WorldEntities is the main edition.

**Цветной свет и мировые тени для Minecraft Java 26.3.**
До **128 источников одновременно**, пять форм света, настройка цвета, яркости, радиуса и направления. Для обычных ламп достаточно ресурспака и команд. Основная версия — WorldEntities.

**[Download / Скачать](https://github.com/JagerMeistars/Chroma/releases/latest)** · **[Русская инструкция](docs/README.ru.md)** · **[English guide](docs/README.en.md)**

## Start / Начать

1. Put `Chroma-Shadows-Dynamic-26.3.zip` in `minecraft/resourcepacks` and enable it. / Положи ZIP в `minecraft/resourcepacks` и включи его.
2. Enable **Improved Transparency** and use only one Chroma pack. / Включи **Improved Transparency** и оставь активным только один Chroma.
3. Open the guide above for a ready-to-copy summon command, all five shapes and settings. / В инструкции выше есть готовая команда создания, все пять видов и настройки.

The optional `Chroma-Flashlight-Test-26.3.zip` adds a player-following flashlight. Its installation and two control commands are in the same guide. / Необязательный датапак фонарика следует за игроком; установка и команды — в той же инструкции.

Lighting is visual: it does not change mob spawning or block light levels. Dynamic shadows use geometry already seen by the camera; hidden changes can remain unknown. / Свет визуальный: он не меняет спавн мобов и уровень освещения блоков. Тени используют уже увиденную геометрию; изменения за камерой могут оставаться неизвестными.

## Development / Разработка

Build with Python 3; no extra packages are needed for these commands:

```sh
python tools/build.py
python tools/build_flashlight.py
```

ZIPs are written to `dist/`. / ZIP-файлы появятся в `dist/`.

- [Build and validation tools / Сборка и проверки](https://github.com/JagerMeistars/Chroma/blob/main/tools/README.md)
- [Technical shadow reference / Техническая справка по теням](https://github.com/JagerMeistars/Chroma/blob/main/docs/SHADOWS.md)
- [Archived Auto edition without shadows / Прежний Auto без теней](https://github.com/JagerMeistars/Chroma/tree/codex/auto)
- [Credits and provenance / Авторы и происхождение](CREDITS.md)
