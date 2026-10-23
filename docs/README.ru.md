# Chroma — инструкция для игрока

Цветной свет и мировые тени для **Minecraft Java 26.3**. Мод не требуется. [English](README.en.md).

## Установка

1. Скачайте `Chroma-26.3.zip`: [стабильную версию](https://github.com/JagerMeistars/Chroma/releases/latest) или [экспериментальную с картами нормалей](https://github.com/JagerMeistars/Chroma/releases/tag/26.3-experimental).
2. Поместите ZIP в `minecraft/resourcepacks` и включите **только один Chroma** с наивысшим приоритетом в **Настройки → Наборы ресурсов**. Каждый игрок, которому нужен эффект, должен включить пак у себя.
3. Включите **Improved Transparency**. После замены пака нажмите **F3+T**.

## Создание первой лампы

Нужны творческий режим и разрешённые читы или права оператора. На выделенном сервере включите `enable-command-block=true`. Длинную команду создания используйте в командном блоке:

```mcfunction
/give @s minecraft:command_block
```

Поставьте блок, вставьте команду ниже **без начального `/`** и активируйте его кнопкой один раз. `~ ~2 ~` означает два блока над командным блоком. Остальные команды инструкции можно вводить в чат.

```mcfunction
/summon minecraft:item_display ~ ~2 ~ {Tags:["chroma.demo","chroma.demo.warm"],Rotation:[0f,0f],billboard:"fixed",item_display:"none",view_range:4f,width:0f,height:0f,item:{id:"minecraft:paper",count:1,components:{"minecraft:item_model":"chroma:marker","minecraft:custom_model_data":{colors:[0xFFBC4D]}}},transformation:{translation:[0f,0f,0f],left_rotation:[0f,0f,0f,1f],scale:[8f,0.3f,1f],right_rotation:[0f,0f,0f,1f]}}
```

Появится тёплый источник с видимым ореолом: цвет `0xFFBC4D`, радиус **8 блоков**, яркость **0.3**. Разместите его над полом или возле стены, чтобы увидеть свет. Декоративная модель светильника необязательна.

## Пять форм света

Укажите один из этих ID в `minecraft:item_model`. Одну модель можно использовать у нескольких ламп; назначать номера слотов не нужно.

| ID модели | Форма |
| --- | --- |
| `chroma:marker` | Свет во все стороны |
| `chroma:marker_spot_narrow` | Узкий прожектор |
| `chroma:marker_spot` | Средний прожектор |
| `chroma:marker_spot_wide` | Широкий прожектор |
| `chroma:marker_dome` | Полусфера вниз с лёгким мерцанием |

## Изменение и удаление лампы

Каждая команда ниже действует **только на ближайшую лампу из примера в пределах 16 блоков**. Для отдельных ламп сцены задавайте уникальные теги и подставляйте нужный тег в селектор. Сохраняйте `billboard:"fixed"`, `item_display:"none"` и Z-масштаб `1f`; радиус и яркость должны быть положительными.

```mcfunction
# Цвет: 0xRRGGBB; здесь голубой
/data modify entity @e[type=minecraft:item_display,tag=chroma.demo.warm,distance=..16,sort=nearest,limit=1] item.components."minecraft:custom_model_data".colors set value [0x66CCFF]
# Радиус в блоках
/data modify entity @e[type=minecraft:item_display,tag=chroma.demo.warm,distance=..16,sort=nearest,limit=1] transformation.scale[0] set value 12f
# Яркость
/data modify entity @e[type=minecraft:item_display,tag=chroma.demo.warm,distance=..16,sort=nearest,limit=1] transformation.scale[1] set value 0.15f
# Заменить форму на средний прожектор
/data modify entity @e[type=minecraft:item_display,tag=chroma.demo.warm,distance=..16,sort=nearest,limit=1] item.components."minecraft:item_model" set value "chroma:marker_spot"
# Направить вниз: [yaw, pitch]
/data modify entity @e[type=minecraft:item_display,tag=chroma.demo.warm,distance=..16,sort=nearest,limit=1] Rotation set value [0f,90f]
# Перенести на два блока выше вашей текущей позиции
/tp @e[type=minecraft:item_display,tag=chroma.demo.warm,distance=..16,sort=nearest,limit=1] ~ ~2 ~
# Удалить только эту лампу
/kill @e[type=minecraft:item_display,tag=chroma.demo.warm,distance=..16,sort=nearest,limit=1]
```

Направляйте прожектор через `Rotation`. Полусфера всегда светит вниз.

| Компонента поворота | Значения |
| --- | --- |
| Yaw | `0` юг, `90` запад, `-90` восток, `180` север |
| Pitch | `0` горизонтально, `90` вниз, `-90` вверх |

## Общие настройки

В **экспериментальной версии** все настройки находятся в **`assets/chroma/shaders/include/settings.glsl`**.

Распакуйте пак в папку внутри `resourcepacks`; `pack.mcmeta` и `assets` должны лежать прямо в ней. Включите эту папку **вместо ZIP**. Откройте `settings.glsl` в текстовом редакторе, измените значение после имени настройки, сохраните файл и нажмите **F3+T**.

| Настройка | Значение по умолчанию и действие |
| --- | --- |
| `CHROMA_SHADOWS_ENABLED` | `1`: тени включены; `0`: выключены (свет проходит сквозь стены) |
| `CHROMA_SHADOW_QUALITY` | `2`: обычное качество; `1`: быстрее, но тени грубее |
| `CHROMA_SOURCE_SIZE` | `0.35`: большее значение смягчает края теней |
| `CHROMA_SHADOW_PIXELATE` | `1`: пиксельный свет и тени; `0`: плавный |
| `CHROMA_SHADOW_PIXELS_PER_BLOCK` | `16`: большее значение уменьшает пиксели |
| `CHROMA_NORMAL_MAPS` | `1`: рельеф текстур включён; `0`: выключен |
| `CHROMA_NORMAL_STRENGTH` | `1.0`: сила рельефа; `0.5`: слабее |
| `CHROMA_GLOW_ENABLED` | `1`: ореол лампы включён; `0`: выключен |
| `CHROMA_GLOW_RADIUS` | `0.35`: радиус ореола в блоках |
| `CHROMA_GLOW_STRENGTH` | `0.04`: яркость ореола |
| `CHROMA_GLOW_SOFTNESS` | `1.0`: обычная растушёвка; `0.5`: чётче; `2.0`: мягче |
| `CHROMA_FLICKER_AMOUNT` | `0.12`: мерцание полусферы; `0.0`: выключено |
| `CHROMA_FLICKER_SPEED` | `0.9`: большее значение ускоряет мерцание |

Для повышения FPS попробуйте `CHROMA_SHADOW_QUALITY 1` или выключите тени через `CHROMA_SHADOWS_ENABLED 0`.

## Карты нормалей (экспериментальная версия)

Карты нормалей придают текстурам рельеф под **светом ламп Chroma**. Они включены для непрозрачных ванильных текстур блоков и текстур с вырезами; полупрозрачные текстуры и загружаемые скины голов игроков сохраняют обычный вид. Рельеф не меняет форму блоков.

### Свои текстуры и модели

1. Оставьте обычную текстуру, например `stone.png`. Рядом добавьте `stone_n.png` **того же размера** — карту нормалей OpenGL RGB; плоская нормаль имеет цвет `(128, 128, 255)`. Для текстур блоков без карты она создаётся автоматически.
2. Распакуйте Chroma и откройте терминал в этой папке. С установленным Python выполните:

```shell
python -m pip install numpy Pillow
python tools/normal_maps.py --source MyPack --output MyPack-Chroma
```

3. Положите `MyPack-Chroma` в `resourcepacks`, включите его **выше Chroma** и нажмите **F3+T**. Сохраните исходный пак для редактирования; после изменений запустите конвертацию заново.

Конвертер включён в ZIP Chroma. Для JSON-моделей со своей геометрией привязывайте границы UV к целым пикселям исходной текстуры; поворот и отражение UV поддерживаются. Плоские предметы, форму которых Minecraft создаёт по прозрачности текстуры, сохраняют исходные текстуры и силуэты без рельефа.

## Необязательный фонарик

Скопируйте папку [`datapacks/chroma_flashlight`](https://github.com/JagerMeistars/Chroma/tree/main/datapacks/chroma_flashlight) из репозитория в `datapacks` своего мира и выполните от имени игрока:

```mcfunction
/reload
/function chroma_flashlight:start
```

Остановка: `/function chroma_flashlight:stop`; выполните её перед удалением датапака. Создаётся **один активный фонарик**: белый средний прожектор радиусом 16 и яркостью 0.3, следующий за глазами и направлением владельца. Запуск заменяет прежнего владельца. Фонарик учитывается в лимите света; при резких поворотах возможно небольшое отставание.

## Практические ограничения

- До **128 одновременно отрисовываемых ламп**. Источники должны быть загружены и отрисованы; большое перекрытие света может снижать FPS.
- У объектов, на которые вы ещё не смотрели, тени могут быть неправильными. После перемещения или изменения блоков посмотрите на это место. После смены мира или измерения нажмите **F3+T**.
- Ореол может скрываться, если центр лампы перекрыт стеклом, водой или интерфейсом в мире.
- Chroma учитывает исходный цвет и рисунок поверхности; яркость также зависит от обычного освещения.
- Эффект **только визуальный**: уровень блочного света и появление мобов не меняются.
