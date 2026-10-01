# Chroma — инструкция для игрока

Цветной свет и мировые тени для **Minecraft Java 26.3**. Мод не требуется. [English](README.en.md).

## Установка

1. Скачайте `Chroma-26.3.zip` из [Releases](https://github.com/JagerMeistars/Chroma/releases/latest).
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

Появится невидимая тёплая лампа: цвет `0xFFBC4D`, радиус **8 блоков**, яркость **0.3**. Разместите её над полом или возле стены, чтобы увидеть свет. Декоративная модель светильника необязательна.

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

Для изменения настроек распакуйте пак в папку внутри `resourcepacks`; `pack.mcmeta` и `assets` должны лежать прямо в ней. Включите эту папку **вместо ZIP**, измените файл, сохраните и нажмите **F3+T**.

Редактируйте `assets/chroma/shaders/include/shadow_config.glsl`:

| Настройка | Стандартное значение и действие |
| --- | --- |
| `CHROMA_SHADOW_PIXELATE` | `1`: пиксельный свет и тени; `0`: непрерывная выборка |
| `CHROMA_SHADOW_PIXELS_PER_BLOCK` | `16`: число делений блока при включённой пикселизации |
| `CHROMA_SOURCE_SIZE` | `0.35`: радиус источника; большее значение смягчает тени |
| `CHROMA_SHADOW_SAMPLES` | `16`: обычное качество; `8`: меньше проб, возможен выигрыш скорости, но тени грубее |

Дополнительный туман Chroma выключен по умолчанию (`FOG_DENSITY 0.0` в `assets/chroma/shaders/post/shade.fsh`). Для отключения мерцания полусфер — `CHROMA_FLICKER_AMOUNT 0.0` в `assets/chroma/shaders/include/flicker.glsl`.

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
- Chroma учитывает исходный цвет и рисунок поверхности; яркость также зависит от обычного освещения.
- Эффект **только визуальный**: уровень блочного света и появление мобов не меняются.
