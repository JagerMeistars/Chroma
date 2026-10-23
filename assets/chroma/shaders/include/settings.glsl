#ifndef CHROMA_SETTINGS
#define CHROMA_SETTINGS

// Chroma settings / Настройки Chroma
// Edit values here, save, then press F3+T in Minecraft.
// Измените значения здесь, сохраните файл и нажмите F3+T в Minecraft.

// Shadows / Тени: 0 off / выкл., 1 on / вкл.
#define CHROMA_SHADOWS_ENABLED 1
// 1 faster / быстрее (64x64, 8 samples); 2 normal / обычное (128x128, 16).
#define CHROMA_SHADOW_QUALITY 2
// Larger source = softer shadows / Больше источник = мягче тени.
#define CHROMA_SOURCE_SIZE 0.35
// Pixelated light and shadows / Пикселизация света и теней.
#define CHROMA_SHADOW_PIXELATE 1
#define CHROMA_SHADOW_PIXELS_PER_BLOCK 16

// Normal maps / Карты нормалей. Strength / сила: 0.0 flat / плоско, 1.0 normal.
#define CHROMA_NORMAL_MAPS 1
#define CHROMA_NORMAL_STRENGTH 1.0

// Local lamp halo / Ореол лампы. Radius in blocks / Радиус в блоках.
#define CHROMA_GLOW_ENABLED 1
#define CHROMA_GLOW_RADIUS 0.35
#define CHROMA_GLOW_STRENGTH 0.04
// 0.5 sharper / чётче, 1.0 current / текущий, 2.0 softer / мягче. Range 0.01..2.0.
#define CHROMA_GLOW_SOFTNESS 1.0

// Hemisphere flicker / Мерцание полусферы: amount 0.0 disables / отключает.
#define CHROMA_FLICKER_AMOUNT 0.12
#define CHROMA_FLICKER_SPEED 0.9

// Advanced appearance / Дополнительные настройки внешнего вида.
// All lamp radii multiplier / Множитель радиуса всех ламп.
#define CHROMA_RADIUS_GAIN 1.0
// Overall light and halo intensity / Общая интенсивность света и ореола.
#define INTENSITY_GAIN 70.0
// Surface lighting strength / Сила освещения поверхностей.
#define LIGHT_STRENGTH 0.3
// Film-like brightness compression: 0 off, 1 on / Сжатие яркости: 0 выкл., 1 вкл.
#define ENABLE_ACES 1
// Colour preservation after compression: 0..1 / Сохранение цвета при сжатии: 0..1.
#define TONE_SAT 0.6
// Maximum coloured-light boost / Максимальное усиление цветного света.
#define LOOK_CORE 4.0
// Energy needed for full lighting: higher = subtler / Больше = слабее эффект света.
#define LOOK_FULL_LUM 3.0
// Fraction of radius before fading begins: 0..1 / Доля радиуса до спада света: 0..1.
#define FALLOFF_CORE 0.15
// Cone angle cosines: inner > outer / Косинусы углов конуса: inner > outer.
#define SPOT_COS_INNER 0.95
#define SPOT_COS_OUTER 0.88
#define SPOT_NARROW_COS_INNER 0.985
#define SPOT_NARROW_COS_OUTER 0.96
#define SPOT_WIDE_COS_INNER 0.88
#define SPOT_WIDE_COS_OUTER 0.74
// Hemisphere edge softness: higher = softer / Мягкость края полусферы: больше = мягче.
#define DOME_EDGE 0.25

// Advanced shadows / Дополнительные настройки теней.
// 0 follows quality / по качеству; 8 or 16 fixes the filter sample count.
#define CHROMA_FILTER_SAMPLES_OVERRIDE 0
// 1 immediate / каждый кадр; 8 staggered / по очереди за 8 кадров.
#define CHROMA_SHADOW_REFRESH_FRAMES 1
// Experimental adaptive filtering / Экспериментальная адаптивная фильтрация.
#define CHROMA_ADAPTIVE_SHADOWS 0

#endif
