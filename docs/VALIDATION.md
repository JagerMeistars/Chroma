# Automatic Chroma — validation / Проверки

These are measurements from a launched **Minecraft Java 26.3** client, controlled through vanilla APIs and read back directly. **ComputerUse was not used.** Temporary Java test bridges collected frame intervals and inspected GPU output; they are not included in the resource pack and are not required to use it.

Это результаты запущенного **Minecraft Java 26.3**, которым управляли через обычные API игры и из которого напрямую считывали данные. **ComputerUse не использовался.** Временные Java-модули проверки собирали интервалы кадров и читали результат GPU; они не входят в ресурспак и не нужны для его использования.

## Recorded performance / Измеренная производительность

**These timings were collected from the previous 32-source build. The current build has a 128-source budget. The user reports good performance at 64 sources; the 128-source build has not been benchmarked.**

**Эти замеры получены на предыдущей сборке с пределом 32 источника. В текущей версии предел — 128 источников. Пользователь сообщил о хорошей производительности на 64; скорость версии на 128 источниках пока не измерялась.**

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

## Functional checks / Проверка работы

**The functional and edge-case live checks below also used the earlier 32-source build. They do not verify this 128-source shader configuration; the updated pack has not been launched or profiled at 128 sources.**

**Игровые функциональные проверки и граничные случаи ниже также выполнены на прежней сборке с пределом 32 источника. Они не подтверждают работу текущей конфигурации шейдеров на 128 источниках; обновлённый пак не запускался и не измерялся с 128 источниками.**

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

The current 128-source assets were checked again on 2026-09-30 with Minecraft 26.3's compiler: **14/14 shaders**. The exact client OpenGL translation produced **114 shader stages**, and the local NVIDIA driver linked **57 core/post program variants** with zero failures. The documented examples passed Minecraft's parsers: **152 commands, 132 summon payloads and 12 detached NBT edits**, no errors. The resource graph has eight post passes, five primary marker models and ten marker textures; its 160 legacy item aliases do not encode source IDs. The supplied RPDREVO hash manifest is unchanged.

Текущие файлы версии на 128 источников повторно проверены 30.09.2026 компилятором Minecraft 26.3: **14 из 14 шейдеров**. Точный путь преобразования OpenGL дал **114 стадий**, драйвер NVIDIA скомпоновал **57 вариантов core/post-программ** без ошибок. Примеры проверены парсерами Minecraft: **152 команды, 132 NBT создания и 12 изменений отдельных копий NBT**, ошибок нет. В графе ресурсов восемь проходов, пять основных моделей и десять текстур маркеров; 160 прежних названий предметов служат совместимости и не задают ID источников. Хеши исходного RPDREVO не изменились.

Evidence / Файлы: `audit/assets.json`, `audit/ValidatePack.log`, `audit/ReproduceClientShaders.log`, `audit/CheckDriver.log`, `audit/examples-validation.json`. These offline checks supplement the real-client tests above; they are not FPS measurements.

## Scope / Границы результата

These runs isolate lighting on a simple loaded floor fixture. Terrain complexity, CPU load, other entities, other packs, resolution, source overlap and hardware can change performance. The current automatic list has a finite **128-source budget**. The user reports good performance at 64 sources; 128 have not been live-tested. The performance samples below are from the previous 32-source build. The internal raw-address capacity is also finite and depends on resolution; a 320 × 240 frame provides **6,240** raw addresses. The earlier live small-window check confirmed collection of 32 sources; 64 sources at small resolutions have not been checked; the current 128-source build has not been live-tested. No claim is made here for Vulkan, rendering mods or arbitrary pack combinations.

Замеры изолируют освещение на простой загруженной сцене с полом. Сложность мира, нагрузка CPU, другие сущности и паки, разрешение, перекрытие источников и оборудование влияют на FPS. У текущего автоматического списка конечный **бюджет 128 источников**. Пользователь сообщил о хорошей производительности на 64 источниках; версия на 128 в игре не проверялась. Замеры производительности выше сделаны на предыдущей сборке с пределом 32 источника. Пространство исходных адресов тоже ограничено разрешением: при 320 × 240 доступно **6240** адресов. В предыдущей версии в этом маленьком окне в игре подтверждён сбор 32 источников; 64 источника при малом разрешении и текущая версия на 128 источников пока не проверялись. Vulkan, моды рендеринга и произвольные сочетания паков здесь не заявлены как проверенные.
