// Current-frame compact light list. Indices are assigned automatically on GPU.
#define CHROMA_LAMPS 128
#define CHROMA_RADIUS_GAIN 1.0

// Each RGBA8 texel stores one uint32 or the raw bits of one float32.
// Camera section: +0 valid, +1..16 projection, +17..32 inverse projection,
// +33..41 view rotation, +42 source count, +43 automatic-address scan bound;
// texels 44..127 are reserved.
// Light records: +0 valid, +1..3 eye position, +4 radius, +5 nominal intensity,
// +6 shape, +7..9 facing, +10 current-frame flag, +11 automatic vertex address,
// +12 render intensity with stable per-colour flicker. Header42=count,43=scan bound.
#define MATDEC_LAMP(k) (128 + (k) * 16)

uint chromaMdBits(sampler2D md, int i) {
    uvec4 b = uvec4(texelFetch(md, ivec2(i, 0), 0) * 255.0 + 0.5);
    return b.r | (b.g << 8) | (b.b << 16) | (b.a << 24);
}
float chromaMdFloat(sampler2D md, int i) { return uintBitsToFloat(chromaMdBits(md, i)); }
bool chromaMdValid(sampler2D md, int base) { return chromaMdBits(md, base) == 1u; }

mat4 chromaMdInvProj(sampler2D md, int base) {
    mat4 m;
    for (int i = 0; i < 16; i++) m[i / 4][i % 4] = chromaMdFloat(md, base + 17 + i);
    return m;
}
mat3 chromaMdRot(sampler2D md, int base) {
    mat3 m;
    for (int i = 0; i < 9; i++) m[i / 3][i % 3] = chromaMdFloat(md, base + 33 + i);
    return m;
}
bool chromaMdLampOn(sampler2D md, int k) { return chromaMdBits(md, MATDEC_LAMP(k)) == 1u; }
vec3 chromaMdLampEyeOf(sampler2D md, int k) {
    return vec3(chromaMdFloat(md, MATDEC_LAMP(k) + 1), chromaMdFloat(md, MATDEC_LAMP(k) + 2),
                chromaMdFloat(md, MATDEC_LAMP(k) + 3));
}
float chromaMdLampRadiusOf(sampler2D md, int k) { return chromaMdFloat(md, MATDEC_LAMP(k) + 4); }
float chromaMdLampIntensityOf(sampler2D md, int k) { return chromaMdFloat(md, MATDEC_LAMP(k) + 5); }
int chromaMdLampShapeOf(sampler2D md, int k) { return int(chromaMdBits(md, MATDEC_LAMP(k) + 6)); }
vec3 chromaMdLampFacingOf(sampler2D md, int k) {
    return vec3(chromaMdFloat(md, MATDEC_LAMP(k) + 7), chromaMdFloat(md, MATDEC_LAMP(k) + 8),
                chromaMdFloat(md, MATDEC_LAMP(k) + 9));
}

float chromaMdRenderIntensity(sampler2D md, int k) { return chromaMdFloat(md, MATDEC_LAMP(k) + 12); }
