# Automatic Chroma — validation / Проверки

These are measurements from a launched **Minecraft Java 26.3** client, controlled through vanilla APIs and read back directly. **ComputerUse was not used.** Temporary Java test bridges collected frame intervals and inspected GPU output; they are not included in the resource pack and are not required to use it.

Это результаты запущенного **Minecraft Java 26.3**, которым управляли через обычные API игры и из которого напрямую считывали данные. **ComputerUse не использовался.** Временные Java-модули проверки собирали интервалы кадров и читали результат GPU; они не входят в ресурспак и не нужны для его использования.

## Current Auto 128 — live checks / Текущий Auto 128 — игровые проверки

**The main, shadow-free Auto 128 build was launched and tested at 1920 × 1080 on 2026-09-30.** All 128 current-frame GPU records retained their unique colours, five light shapes, radii, brightness, positions and directions. The union of the tile masks contained every bit in all four 32-source banks (`ffffffff` in each bank). Three camera positions retained all 128 sources, with world-transform consistency error below **0.000016 blocks**.

Seven removal/restore checks targeted compact-list indices **31, 32, 63, 64, 95, 96 and 127**. Each produced a visible floor contribution: peak channel difference **15–50 / 255**, **135–470 changed floor pixels**, control noise **0–2 / 255**. These are selected bank-boundary contribution checks, **not 128 separate per-source image tests**. Removing all sources cleared the catalogue, counts, indices, decoded records, colours and tile masks; the 128-light fixture was then restored.

**Основная версия Auto 128 без теней запущена и проверена при 1920 × 1080 30.09.2026.** Все 128 записей GPU сохранили уникальные цвета, пять форм света, радиусы, яркость, позиции и направления. Объединение масок участков содержало все биты каждого из четырёх банков по 32 источника (`ffffffff` в каждом). В трёх положениях камеры сохранялись все 128 источников; ошибка согласованности преобразований мира — менее **0,000016 блока**.

Выполнены семь удалений/восстановлений для индексов компактного списка **31, 32, 63, 64, 95, 96 и 127**. В каждом случае подтверждён вклад в изображение пола: максимальная разница канала **15–50 из 255**, **135–470 изменившихся пикселей**, контрольный шум **0–2 из 255**. Это выборочные проверки границ банков, **а не 128 отдельных проверок вклада каждой лампы**. После удаления всех источников обнулились каталог, счётчики, индексы, декодированные записи, цвета и маски участков; затем сцена из 128 ламп восстановлена.

Evidence / Отчёт: `audit/shadows/baseline128-live.json` and `baseline128-live.commands.json`; captures are named in the report. Despite the audit folder name, these checks loaded **`file/Chroma-Auto-128.zip` without shadows**. / Несмотря на название папки отчётов, проверки выполнялись с **`file/Chroma-Auto-128.zip` без теней**.

### Current performance / Текущая производительность

| Build and scene / Сборка и сцена | Average FPS / Средний FPS | 1% low FPS | Median frame, ms / Медиана кадра, мс | P99 frame, ms / P99 кадра, мс | Frames > 6.944 ms / Кадры > 6,944 мс |
| --- | ---: | ---: | ---: | ---: | ---: |
| Auto 128: spread / разнесены | 894.24 | 319.57 | 1.0067 | 2.5758 | 4 / 17885 |

This is the Auto run `final128-spread-auto` from the current comparison fixture: **128 lights**, white floor, camera **`(0, 28, 0)`, yaw `0°`, pitch `90°`**. Minecraft Java 26.3, RTX 4060 Ti, NVIDIA 595.71, OpenGL, **1920 × 1080**, FOV 70, render/simulation distances 8/5. Packs: `vanilla` and `file/Chroma-Auto-128.zip`. The window was unfocused, not minimized, and unpaused; VSync was off, presentation immediate, effective frame limit unlimited, throttle reason `NONE`. Camera and settings matched at the beginning and end.

After **10 seconds of warm-up**, the probe retained **17,885 complete frame intervals over 20.00021 seconds**, with **zero invalid frames** and no GPU readback during measurement. Four frames exceeded the 144 FPS budget. Average and 1% low exceeded 144 FPS in this fixture; this is not a guarantee for every frame, heavy worlds or 128 overlapping lights. The earlier `baseline128-spread` run used a different camera and is not substituted into this table or treated as a direct comparison.

Это прогон Auto `final128-spread-auto` из текущей сравнительной сцены: **128 ламп**, белый пол, камера **`(0, 28, 0)`, yaw `0°`, pitch `90°`**. Minecraft Java 26.3, RTX 4060 Ti, NVIDIA 595.71, OpenGL, **1920 × 1080**, FOV 70, дальность прорисовки/симуляции 8/5. Включены `vanilla` и `file/Chroma-Auto-128.zip`. Окно было без фокуса, не свёрнуто, игра не на паузе; VSync выключен, вывод немедленный, ограничение FPS снято, причина троттлинга `NONE`. Камера и настройки в начале и конце совпали.

После **10 секунд прогрева** записано **17 885 полных интервалов кадров за 20,00021 секунды**, **некорректных кадров — ноль**; считывания GPU во время замера не было. Четыре кадра превысили бюджет для 144 FPS. Средний FPS и 1% low выше 144 в этой сцене; это не гарантия для каждого кадра, тяжёлого мира или 128 перекрывающихся ламп. Ранний прогон `baseline128-spread` использовал другую камеру и не подставляется в таблицу как прямое сравнение.

Evidence / Файлы: `audit/shadows/benchmark/results/final128-spread-auto.json` and `.csv`; earlier separate-view run / ранний прогон с другим ракурсом: `audit/shadows/benchmark/results/baseline128-spread.json` and `.csv`. These Auto results do not establish shadow performance; separate shadow benchmarking is still being completed. / Результаты Auto не подтверждают производительность теней; отдельные замеры версий с тенями ещё выполняются.

## Historical 32-source performance / Прежние замеры 32 источников

The following measurements belong to the earlier **32-source** builds and are retained as historical comparisons. / Следующие замеры относятся к прежним сборкам на **32 источника** и сохранены для истории сравнений.

| Build and scene / Сборка и сцена | Average FPS / Средний FPS | 1% low FPS | Median frame, ms / Медиана кадра, мс | P99 frame, ms / P99 кадра, мс | Frames > 6.944 ms / Кадры > 6,944 мс |
| --- | ---: | ---: | ---: | ---: | ---: |
| Old / Старый: spread / разнесены | 512.9 | 281.9 | 1.853 | 3.146 | 2 / 10257 |
| Auto / Новый: spread / разнесены | 1713.7 | 522.2 | 0.520 | 1.488 | 0 / 34275 |
| Old / Старый: overlap / перекрытие | 278.9 | 171.6 | 3.411 | 5.473 | 1 / 5577 |
| Auto / Новый: overlap / перекрытие | 390.3 | 227.1 | 2.442 | 4.009 | 1 / 7805 |

The overlapping-source run improved average FPS from **278.9 to 390.3** (about **40%**) and 1% low from **171.6 to 227.1**. The objective was a 144 FPS frame budget (6.944 ms). The new overlapping run exceeded that budget on 1 of 7,805 frames; its average and 1% low were above 144 FPS. This is a result for the test fixture, not a guarantee that every frame or arbitrary Minecraft world stays above 144 FPS. For dispersed sources, the previous 32-source automatic build measured **1713.7 FPS average / 522.2 FPS 1% low**, versus **512.9 / 281.9** for the old build: approximately **3.34× average FPS**. None of the final spread run's 34,275 sampled frames exceeded 6.944 ms.

В сцене с перекрытием средний FPS вырос с **278,9 до 390,3** — примерно на **40%**, а 1% low с **171,6 до 227,1**. Цель — бюджет кадра для 144 FPS, то есть 6,944 мс. В новом прогоне с перекрытием его превысил 1 кадр из 7805; средний FPS и 1% low оказались выше 144. Это результат конкретной тестовой сцены, а не гарантия 144 FPS для каждого кадра и произвольного мира Minecraft. Для разнесённых источников предыдущая автоматическая сборка с пределом 32 источника показала **1713,7 FPS в среднем / 522,2 FPS 1% low**, старая — **512,9 / 281,9**: средний FPS выше примерно в **3,34 раза**. Ни один из 34 275 кадров итогового разнесённого прогона не превысил 6,944 мс.

### Exact conditions / Условия

- Minecraft Java 26.3; **NVIDIA GeForce RTX 4060 Ti**, NVIDIA driver **595.71**, **OpenGL** backend; actual framebuffer **1920 × 1080**.
- Isolated `chroma-direct-audit-26.3` instance, loaded void-world floor fixture, 32 lamps; packs `vanilla` and `file/Chroma`. Same scene and fixed viewpoint within each before/after pair. Spread camera: `(23.5, 23, 34.5)`, yaw `-180°`, pitch `43°`; overlap camera: `(23.5, 4, 20.5)`, yaw `-180°`, pitch `25°`.
- FOV `70`; render distance `8`; simulation distance `5`; HUD hidden. VSync off, immediate presentation. The option value **260 means unlimited** in this exact client; it is not a 260 FPS cap. Effective throttle reason: `NONE`.
- The window was **not focused** (`focused:false`), **not minimized** (`iconified:false`) and the game was **not paused**. A temporary direct-API input lock kept the viewpoint fixed. These are unfocused-window measurements, not a claim of a separate focused-window test.
- **10 seconds warm-up + 20 seconds measurement** per run. Every complete end-of-frame wall interval after submission, presentation and the frame limiter was retained. No synchronous GPU readback occurred during sampling; invalid frame count was zero. GPU timer queries were not enabled, so these are complete frame-interval measurements, not GPU-only timings.
- Average FPS is frame count divided by elapsed sample time. **1% low** is the inverse mean duration of the slowest 1% of frame intervals; P99 is a frame-time percentile and is not the same statistic.

Русская версия условий: отдельный экземпляр игры с полом в пустом мире, 32 лампы; RTX 4060 Ti / OpenGL / драйвер 595.71, реальный кадр 1920 × 1080. FOV 70, дальность прорисовки 8, симуляции 5, HUD скрыт, VSync выключен, ограничение FPS снято. Окно было без фокуса, но не свёрнуто, игра не стояла на паузе. В каждой сравниваемой паре сохранялись сцена и камера. После 10 секунд прогрева записывались все интервалы кадров за 20 секунд; считывания изображения с GPU во время замера не было. Это полное время кадра, а не изолированное время GPU. 1% low вычислен по средней длительности самого медленного процента кадров.

Raw evidence in the development workspace / Исходные данные в рабочей папке:

- `audit/slotless/benchmark/results/original32-spread-b.json` and `.csv`
- `audit/slotless/benchmark/results/automatic32-spread-final.json` and `.csv`
- `audit/slotless/benchmark/results/original32-overlap-a.json` and `.csv`
- `audit/slotless/benchmark/results/automatic32-overlap-a.json` and `.csv`

## Historical 32-source functional checks / Прежние проверки 32 источников

**The checks below used the earlier 32-source build. Their broader per-source, coincidence and small-window coverage must not be attributed to the current 128-source configuration; the separate current checks are documented above.**

**Проверки ниже выполнены на прежней сборке с пределом 32 источника. Их более широкую проверку вклада каждой лампы, совпадающих источников и маленького окна нельзя переносить на текущую конфигурацию 128; её отдельные проверки описаны выше.**

The full direct-client audit **passed** at 1920 × 1080:

- **32 mixed sources:** repeated use of only the five primary model names, with 32 distinct colours. Current-frame GPU records retained each source's colour, shape, radius, intensity, position and direction.
- **Each source contributes to the actual rendered surface:** all 32 were removed and restored individually. Each removal left the other 31 sources and the camera unchanged. In the corresponding floor area, the maximum colour-channel difference was **68–167 / 255**, versus a control-image noise peak of **7 / 255**; at least **1,142 pixels** changed above the noise threshold for every source. Transport pixels were excluded from the image comparison.
- **32 instances of each reusable model:** five rounds, 160 source/form instances. Correct GPU colours, shapes, transforms and downward spotlight axes were verified. This checks automatic collection with repeated identical model IDs.
- **Coincident sources:** all 32 records remained independent when placed at one position, both with different colours/forms and with completely identical colour, form and position. The identical case still had 32 distinct automatic addresses.
- **Moving camera and changing ordinary geometry:** 16 views, with 0–160 additional ordinary paper displays. All 32 lights remained present across **16 distinct automatic-address sets**, up to raw address **9023**. Position consistency error stayed below **0.00001 blocks**. The original mixed scene was restored successfully.

Полная проверка через API клиента **пройдена** при 1920 × 1080:

- **32 разных источника** использовали только пять повторяемых названий моделей и 32 цвета. В текущих записях GPU проверены цвет, форма, радиус, яркость, позиция и направление каждого источника.
- **Отдельный вклад каждого источника в изображение:** все 32 по очереди удаляли и восстанавливали. Остальные 31 источник и камера оставались неизменными. Максимальная разница цветового канала на соответствующем участке пола составляла **68–167 из 255** при контрольном шуме **7 из 255**; для каждого источника выше порога шума менялось не менее **1142 пикселей**. Служебные пиксели транспорта исключены из сравнения.
- **По 32 экземпляра каждой модели:** пять прогонов, 160 сочетаний источника и формы. Проверены данные цвета/формы/преобразований и направление прожекторов вниз, при многократном использовании одинакового названия модели.
- **Источники в одной точке:** сохранены все 32 записи — как с разными цветами/формами, так и с полностью одинаковыми цветом, формой и позицией. Даже одинаковые источники получили 32 разных автоматических адреса.
- **Движение камеры и обычная геометрия:** 16 ракурсов и от 0 до 160 дополнительных дисплеев обычной бумаги. Все 32 лампы сохранялись при **16 разных наборах автоматических адресов**, вплоть до адреса **9023**. Ошибка согласованности позиций была ниже **0,00001 блока**. Исходная сцена успешно восстановлена.

Evidence / Отчёт: `audit/slotless/functional-verification.json`, command results in `functional-verification.commands.json`, and captures named in the report. GPU readback was used for these functional checks, separately from the timed performance runs. The floor-image comparison used the known test-floor plane and the actual decoded inverse projection; it did not substitute synthetic rendered lighting for the game image.

Для функциональной проверки данные считывались с GPU отдельно от замеров FPS. Участки пола для сравнения определялись по известной плоскости тестового пола и фактической обратной матрице проекции; сравнивались изображения настоящего клиента, а не синтетически отрисованное освещение.

### Edge cases / Граничные случаи

A separate live check passed (`audit/slotless/edge-verification.json`): with **zero sources**, the camera-valid flag, catalogue count and working-list count became zero, with no stale colours; with **33 sources**, the catalogue counted 33 while the 32-source prototype working list stayed at its former limit of 32; at **320 × 240**, all 32 sources remained valid and all RGB colours matched exactly. The framebuffer was then restored to 1920 × 1080. The small-window check verifies collection and colours, not a full small-window visual-quality or FPS benchmark.

Отдельная игровая проверка пройдена (`audit/slotless/edge-verification.json`): при **нуле источников** флаг камеры, число записей каталога и рабочего списка обнулились, старых цветов не осталось; при **33 источниках** каталог содержал 33 записи, рабочий список старого прототипа — прежний предел 32; при **320 × 240** все 32 источника сохранили корректные записи и точные RGB-цвета. Затем кадр вернули к 1920 × 1080. Проверка маленького окна подтверждает сбор и цвета, но не заменяет отдельную визуальную проверку всех эффектов или замер FPS в этом разрешении.

## Final offline checks / Итоговые проверки файлов

The main, shadow-free Auto 128 assets were checked again on 2026-09-30 with Minecraft 26.3's compiler: **14/14 shaders**. The exact client OpenGL translation produced **114 shader stages**, and the local NVIDIA driver linked **57 core/post program variants** with zero failures. The documented examples passed Minecraft's parsers: **152 commands, 132 summon payloads and 12 detached NBT edits**, no errors. The resource graph has eight post passes, five primary marker models and ten marker textures; its 160 legacy item aliases do not encode source IDs. The supplied RPDREVO hash manifest is unchanged.

Файлы основной версии Auto 128 без теней повторно проверены 30.09.2026 компилятором Minecraft 26.3: **14 из 14 шейдеров**. Точный путь преобразования OpenGL дал **114 стадий**, драйвер NVIDIA скомпоновал **57 вариантов core/post-программ** без ошибок. Примеры проверены парсерами Minecraft: **152 команды, 132 NBT создания и 12 изменений отдельных копий NBT**, ошибок нет. В графе ресурсов восемь проходов, пять основных моделей и десять текстур маркеров; 160 прежних названий предметов служат совместимости и не задают ID источников. Хеши исходного RPDREVO не изменились.

Evidence / Файлы: `audit/assets.json`, `audit/ValidatePack.log`, `audit/ReproduceClientShaders.log`, `audit/CheckDriver.log`, `audit/examples-validation.json`. These offline checks supplement the real-client tests above; they are not FPS measurements.

## Scope / Границы результата

These runs isolate shadow-free lighting on simple loaded floor fixtures. Terrain complexity, CPU load, other entities, other packs, resolution, source overlap and hardware can change performance. The current automatic list has a finite **128-source budget**, live-tested at **1920 × 1080** as detailed above. The internal raw-address capacity is also finite and depends on resolution; a 320 × 240 frame provides **6,240** raw addresses. The earlier small-window check confirmed collection of **32 sources only**; 64/128 sources at small resolutions have not been checked. The historical 32-source overlap results are not a 128-source overlap test. No claim is made here for shadow-edition FPS, Vulkan, rendering mods or arbitrary pack combinations.

Замеры изолируют освещение без теней на простых загруженных сценах с полом. Сложность мира, нагрузка CPU, другие сущности и паки, разрешение, перекрытие источников и оборудование влияют на FPS. У текущего автоматического списка конечный **бюджет 128 источников**, проверенный в игре при **1920 × 1080**, как описано выше. Пространство исходных адресов тоже ограничено разрешением: при 320 × 240 доступно **6240** адресов. Прежняя проверка маленького окна подтверждает сбор **только 32 источников**; 64/128 источников при малом разрешении не проверялись. Прежние результаты перекрытия 32 ламп не являются тестом перекрытия 128. FPS вариантов с тенями, Vulkan, моды рендеринга и произвольные сочетания паков здесь не заявлены как проверенные.
