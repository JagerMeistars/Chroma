# Development checks

These tools are excluded from the resource-pack ZIP. The pack itself requires no
Java agent, mod, script or datapack.

`main` builds WorldEntities Dynamic; the previous shadow-free Auto sources are on
`codex/auto`. Building the RP and optional flashlight ZIP requires only Python
and its standard library:

```powershell
python tools/build.py
python tools/build_flashlight.py
```

Outputs: `dist/Chroma-Shadows-Dynamic-26.3.zip` and
`dist/Chroma-Flashlight-Test-26.3.zip`. For CPU checks and Static export, install
`python -m pip install -r requirements-dev.txt` (NumPy, Pillow, nbtlib). Native
checks additionally use the installed Minecraft 26.3/PrismLauncher Java libraries;
`check_native.py --prism PATH` selects that installation.

1. `python tools/check_assets.py` validates resources, marker encoding and the
   automatic post chain against the installed client JAR. Optional provenance
   comparison requires both inputs: `--source PATH_TO_RPDREVO
   --source-manifest PATH_TO_SAVED_MANIFEST.json`; the local original manifest
   is not included in Git.
2. `python tools/check_native.py` compiles with the installed Minecraft 26.3
   shaderc/SPIR-V pipeline, translates the actual core/post variants, links them
   on a hidden local OpenGL context, and parses the documented commands with
   Minecraft's command/NBT codecs. Use `--pack PATH_TO_ZIP` to validate a built
   variant. It does not launch the game, prove visual quality or measure FPS.
3. `python tools/build.py` builds the main WorldEntities Dynamic ZIP through
   `build_shadows.py`. Legacy Auto is built separately from `codex/auto`.
4. `python tools/check_shadow_math.py` reads `shadow_filter_static.glsl` and
   retains the Static/historical quarter-cell filter reference; it does not
   validate Dynamic PCSS. `python tools/check_voxel_space.py` checks world-space
   sampling/storage; `python tools/check_voxel_geometry.py` checks analytic
   depth fixtures and current acquisition source contracts. None executes GLSL.
5. `python tools/check_transport.py` checks generated shader parity, the camera-header ABI and packet pixel bounds; it does not execute GLSL.
6. `python tools/check_surfel_voxels.py` and
   `python tools/check_surfel_acquisition.py` cover the current Dynamic CPU
   references: four finite planes per cell, quantized plane encoding,
   `4 × 4` patch masks, ray intersections, protected positive evidence,
   full-footprint vacancy checks and overflow/slot reuse. Acquisition checks
   include shared supported normals, rejection of adjacent-face/patch evidence,
   and full-patch proof for mixed clear/unknown probes without losing positive
   priority. Normal-cache controls cover the shared native stencil/support flags,
   15+15-bit encoding, exact axes, quantization error, current-frame pass ordering
   and Static exclusion. The sampled CPU maximum vector error is about `0.000125`;
   this is not exact floating-point equivalence or a live speed measurement.
   Independent analytic fixtures and replayed native depth stencils do not
   execute GLSL or Minecraft.
7. `python tools/check_pcss.py` checks the current Dynamic hybrid filter:
   independent analytic radial planes/half-planes, octahedral seams, contact
   hardening, bounded bias, finite/embedded/zero-radius cases, receiver
   hemispheres, moving origins and the tangent-basis transition regression.
   Source contracts cover the restored finite-atlas helpers, Static wrapper,
   pixelation API and 16-tap default. It does not execute GLSL or measure FPS.
8. `python tools/check_voxel_lod_retention.py` checks persistent first-LOD phase
   updates and full rebuilds when the cache window moves.
9. `python tools/check_entity_mask.py` checks native entity pipeline/alpha
   contracts and mode/Static/OIT guards. WorldEntities2 uses mode `1`, so ordinary
   entity surfaces remain world-caster evidence and the screen path is inactive.
10. `python tools/check_vacancy_depth_bound.py` checks the single-level `256 × 256`
    runtime depth bound, captured native/bobbing projections, unknown-pixel
    guards and equivalence with independent exact vacancy scans. Its additional
    coarse-level math controls are an audit reference, not the shipped path.
    These CPU checks do not execute GLSL or measure FPS.
11. `python tools/check_marker_identity.py` checks complete marker codes, the
    light-blue-wool atlas-border regression and GUI exclusion against the installed
    Minecraft 26.3 JAR (NumPy and Pillow required). `python tools/check_shadow_response.py`
    checks additive-light independence from native ambient lighting, colour mixing
    and bounded shadow response. Neither check executes GLSL or measures FPS.

Current Dynamic flow is camera depth → persistent finite-surface geometry cache
→ source radial-depth maps and `shadow_surface` atlas → hybrid filtering.
WorldEntities2 keeps entity casters in this world cache. Current-frame tile-depth
bounds accelerate vacancy maintenance; uncertain regions retain exact pixel
checks. Kernels up to half a local angular map texel use one finite-geometry
ray; half to one texel smoothly blends it with PCSS; wider kernels use PCSS.
The finite candidate set and observed-geometry limits remain. Legacy Auto remains on `codex/auto`; Static shadow geometry is unchanged; its builds share the WorldEntities2 marker and lighting fixes. The accepted VacancyBounds1b results are recorded in
[shadow validation](../docs/SHADOW_VALIDATION.md); historical screen-mode
experiments are documented in [research](../docs/SHADOW_RESEARCH.md).

`generate_pack.py` regenerates only the five primary marker models, their legacy
aliases, ten marker textures, atlas, transport helpers and native core hooks from
the installed client JAR. It preserves
the lighting shaders and post chain.
Use `--output PATH` to compare regenerated files before replacing them.

The real-client functional audit is a historical 32-source helper at `live/verify_slotless.py --run`; it does not test the current 128-source build. It needs the
prepared isolated Chroma instance and explicitly attached test bridges described
in [live/README.md](live/README.md) and [live/bench-README.md](live/bench-README.md).
It refuses an active benchmark and restores its scene after checking all 32
individual contributions, five shapes, coincident lights and camera/address
changes. Do not run it against a user's normal world.

Historical 32-source live reports are in `audit/slotless/functional-verification.json`,
`audit/slotless/edge-verification.json` and `audit/slotless/benchmark/results`.
The previous slotted renderer's synthetic tests are preserved with its backup
under `audit/slotless/previous-root/tools`; they do not test this transport ABI.

## Русский

Эти инструменты не входят в ZIP ресурспака. Для самого пака не нужны Java-агент,
мод, скрипт или датапак.

В `main` находится WorldEntities Dynamic, прежний Auto без теней — в
`codex/auto`. Для сборки нужны только Python и стандартная библиотека:
`python tools/build.py` создаёт `dist/Chroma-Shadows-Dynamic-26.3.zip`,
`python tools/build_flashlight.py` — `dist/Chroma-Flashlight-Test-26.3.zip`.
Для CPU-проверок и экспорта Static установите зависимости командой
`python -m pip install -r requirements-dev.txt` (NumPy, Pillow, nbtlib). Штатные
проверки дополнительно используют установленные Java-библиотеки Minecraft 26.3
и PrismLauncher; путь задаётся через `check_native.py --prism PATH`.

1. `python tools/check_assets.py` проверяет ресурсы, кодирование маркеров
   и цепочку постобработки по установленному клиентскому JAR. Необязательное
   сравнение исходного пака требует двух параметров: `--source PATH_TO_RPDREVO
   --source-manifest PATH_TO_SAVED_MANIFEST.json`. Локальный исходный манифест
   не входит в Git.
2. `python tools/check_native.py` использует установленный компилятор
   shaderc/SPIR-V Minecraft 26.3, преобразует варианты основных шейдеров и
   постобработки, связывает их в скрытом локальном контексте OpenGL и разбирает
   команды из документации штатными кодеками команд/NBT. `--pack PATH_TO_ZIP`
   выбирает собранный вариант. Проверка не запускает игру, не подтверждает
   визуальное качество и не измеряет FPS.
3. `python tools/build.py` собирает основной WorldEntities Dynamic через
   `build_shadows.py`. Прежний Auto собирается отдельно из `codex/auto`.
4. `python tools/check_shadow_math.py` читает `shadow_filter_static.glsl` и
   сохраняет модель Static/прежнего фильтра ячеек в четверть блока; Dynamic PCSS
   он не проверяет. `python tools/check_voxel_space.py` проверяет координаты и
   хранение, `python tools/check_voxel_geometry.py` — аналитические сцены глубины
   и соответствие текущего кода сбора геометрии. GLSL они не выполняют.
5. `python tools/check_transport.py` проверяет соответствие генерируемых
   шейдеров, формат заголовка камеры и границы служебных пикселей; GLSL не выполняется.
6. `python tools/check_surfel_voxels.py` и
   `python tools/check_surfel_acquisition.py` проверяют текущие CPU-модели Dynamic:
   четыре конечные плоскости в ячейке, квантование, маски `4 × 4`, пересечения
   лучей, защиту положительных наблюдений, полные пиксельные следы при удалении,
   переполнение и повторное использование слотов. Проверки сбора включают общие
   подтверждённые нормали, отбрасывание свидетельств с соседних граней/участков
   и полную проверку участка при смеси пустых и неизвестных проб с сохранением
   приоритета положительных наблюдений. Проверки кеша нормалей охватывают общие
   штатные пробы/признаки поддержки, формат 15+15 бит, точные оси, ошибку квантования,
   порядок проходов текущего кадра и отсутствие прохода в Static. Максимальная
   ошибка вектора в CPU-выборке — около `0.000125`; это не точная эквивалентность
   вычислений с плавающей точкой и не замер скорости в игре. Независимые
   аналитические сцены и повторный разбор сохранённых проб штатной глубины
   не исполняют GLSL и не запускают Minecraft.
7. `python tools/check_pcss.py` проверяет текущий гибридный фильтр Dynamic:
   независимые аналитические плоскости/полуплоскости, швы октаэдрической карты,
   сужение тени у контакта, ограниченный bias, конечность значений, источник
   внутри препятствия, нулевой радиус, полусферы поверхности, движение начала
   координат и регрессию перехода касательного базиса. Проверки исходника
   охватывают восстановленные функции атласа конечных поверхностей, обёртку
   Static, API пикселизации и стандартные 16 выборок. GLSL не выполняется,
   FPS не измеряется.
8. `python tools/check_voxel_lod_retention.py` проверяет фазы постоянного первого
   LOD и его полную пересборку при перемещении окна кеша.
9. `python tools/check_entity_mask.py` проверяет штатные режимы alpha и условия
   переключателя/Static/OIT. WorldEntities2 использует режим `1`: поверхности
   обычных сущностей остаются свидетельствами мировых препятствий, экранный
   тракт неактивен.
10. `python tools/check_vacancy_depth_bound.py` проверяет рабочую одноуровневую
    сводку `256 × 256`, захваченные штатные проекции с покачиванием, защиту
    неизвестных пикселей и совпадение с независимыми точными проверками пустоты.
    Дополнительные математические контроли крупного уровня — исследовательская
    модель, а не путь поставляемой сборки. GLSL не выполняется, FPS не измеряется.
11. `python tools/check_marker_identity.py` проверяет полный код маркера, регрессию
    на границе текстуры голубой шерсти и исключение интерфейса по установленному
    JAR Minecraft 26.3 (нужны NumPy и Pillow). `python tools/check_shadow_response.py`
    проверяет независимость добавляемого света от штатного фонового освещения,
    смешение цветов и ограниченный отклик тени. Проверки не исполняют GLSL и не измеряют FPS.

Текущая цепочка Dynamic: глубина камеры → постоянный кеш конечных поверхностей
→ радиальные карты глубины источников и атлас `shadow_surface` → гибридный фильтр.
WorldEntities2 сохраняет сущности как препятствия в мировом кеше. Границы глубины
тайлов текущего кадра ускоряют обслуживание кеша; сомнительные области сохраняют
точную пиксельную проверку. Ядро до половины локального углового текселя карты
использует один луч по конечной геометрии; между половиной и одним текселем
результат плавно смешивается с PCSS, более широкое ядро использует PCSS.
Конечный набор кандидатов и ограничения увиденной геометрии остаются. Прежний Auto находится в `codex/auto`; геометрия теней Static не изменена; его сборки получают те же исправления маркеров и света WorldEntities2. Результаты принятого VacancyBounds1b фиксируются в
[отчёте](../docs/SHADOW_VALIDATION.md); прежние экранные эксперименты — в
[исследовании](../docs/SHADOW_RESEARCH.md).

`generate_pack.py` повторно создаёт из установленного клиентского JAR только пять
основных моделей маркеров, старые псевдонимы, десять текстур, атлас, передачу
данных и обработчики основных шейдеров. Освещение и цепочка постобработки
сохраняются. `--output PATH` позволяет сравнить результат до замены файлов.

Историческая проверка клиента `live/verify_slotless.py --run` проверяет 32
источника, а не текущую сборку на 128. Ей нужны отдельный подготовленный экземпляр
Chroma и явно подключённые тестовые мосты из
[live/README.md](live/README.md) и [live/bench-README.md](live/bench-README.md).
Она отказывается работать во время активного бенчмарка, проверяет вклад каждого
из 32 источников, пять форм, совпадающие лампы и изменения камеры/адресации,
затем восстанавливает сцену. Не запускайте её в обычном пользовательском мире.

Исторические отчёты находятся в `audit/slotless/functional-verification.json`,
`audit/slotless/edge-verification.json` и `audit/slotless/benchmark/results`.
Синтетические проверки прежнего рендерера с назначаемыми слотами сохранены с его
копией в `audit/slotless/previous-root/tools`; текущий формат передачи данных они
не проверяют.
