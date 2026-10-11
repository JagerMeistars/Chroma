#ifndef CHROMA_NORMAL_MATERIAL
#define CHROMA_NORMAL_MATERIAL
#include <chroma:normal_encoding.glsl>

struct ChromaMaterial {
    vec4 color;
    vec3 tangentNormal;
    bool mapped;
};

// Each prepared texel is a 4x4 tile of identical RGB. Every 2x2 quadrant has
// exactly one alpha-zero corner: its position carries two normal-map bits.
// Binary alpha keeps Minecraft's CPU material classifier out of the translucent
// pass. Mean mipmaps have alpha=191 while retaining the original colour.
bool chromaReadNormalTile(sampler2D atlas, ivec2 origin, out int code, out float coverage) {
    code = 0;
    coverage = 0.0;
    ivec2 size = textureSize(atlas, 0);
    if (any(lessThan(origin, ivec2(0))) || any(greaterThanEqual(origin + 3, size))) return false;
    vec3 reference = texelFetch(atlas, origin, 0).rgb;
    for (int quad = 0; quad < 4; ++quad) {
        ivec2 base = origin + ivec2(quad % 2, quad / 2) * 2;
        int hole = 0;
        float values[4];
        float largest = 0.0, smallest = 256.0, sum = 0.0;
        for (int corner = 0; corner < 4; ++corner) {
            vec4 pixel = texelFetch(atlas, base + ivec2(corner % 2, corner / 2), 0);
            if (any(greaterThan(abs(pixel.rgb - reference), vec3(0.5 / 255.0)))) return false;
            float a = floor(pixel.a * 255.0 + 0.5);
            values[corner] = a;
            largest = max(largest, a);
            sum += a;
            if (a < smallest) { smallest = a; hole = corner; }
        }
        // Animation interpolation blends alpha too in 26.3. Two fully covered
        // corners and a complementary pair still have exactly three texels'
        // coverage, so choose the nearer frame without disabling animation.
        // Ignore near-transparent native overlays (pumpkin blur, destruction).
        // Prepared animation texels this faint are below native cutout anyway.
        if (largest < 6.0 || abs(sum - 3.0 * largest) > 2.0) return false;
        int fullCorners = 0;
        for (int corner = 0; corner < 4; ++corner)
            if (values[corner] >= largest - 1.0) ++fullCorners;
        if (fullCorners < 2) return false;
        if (quad == 0) coverage = largest / 255.0;
        else if (abs(largest - coverage * 255.0) > 1.0) return false;
        code |= hole << (quad * 2);
    }
    return code < 225;
}

bool chromaNormalHoleCandidate(sampler2D atlas, ivec2 pixel) {
    ivec2 size = textureSize(atlas, 0);
    if (any(lessThan(pixel, ivec2(0))) || any(greaterThanEqual(pixel, size))) return false;
    vec4 centre = texelFetch(atlas, pixel, 0);
    if (centre.a >= 254.5 / 255.0) return false;
    int neighbours = 0;
    for (int side = 0; side < 4; ++side) {
        ivec2 offset = side == 0 ? ivec2(1, 0) : side == 1 ? ivec2(-1, 0) :
                       side == 2 ? ivec2(0, 1) : ivec2(0, -1);
        ivec2 adjacent = pixel + offset;
        if (any(lessThan(adjacent, ivec2(0))) || any(greaterThanEqual(adjacent, size))) continue;
        vec4 value = texelFetch(atlas, adjacent, 0);
        if (value.a >= 254.5 / 255.0 &&
                all(lessThanEqual(abs(value.rgb - centre.rgb), vec3(0.5 / 255.0)))) ++neighbours;
    }
    // Every binary transport hole touches two covered texels of its own tile.
    // Transparent native skins/voids normally stop here, before the phase scan.
    return neighbours >= 2;
}

float chromaMipCoverage(sampler2D atlas, vec2 uv, float lod, float originalCoverage) {
    int level = clamp(int(floor(lod)), 1, 4);
    ivec2 size = textureSize(atlas, level);
    while (level > 0 && size.x == 0) { --level; size = textureSize(atlas, level); }
    if (level == 0) return originalCoverage;
    ivec2 pixel = clamp(ivec2(uv * vec2(size)), ivec2(0), size - 1);
    float alpha = texelFetch(atlas, pixel, level).a;
    if (level < 4) {
        ivec2 nextSize = textureSize(atlas, level + 1);
        if (nextSize.x > 0) {
            ivec2 nextPixel = clamp(ivec2(uv * vec2(nextSize)), ivec2(0), nextSize - 1);
            alpha = mix(alpha, texelFetch(atlas, nextPixel, level + 1).a, fract(lod));
        }
    }
    return clamp(alpha * (255.0 / 191.0), 0.0, 1.0);
}

ChromaMaterial chromaSampleMaterial(sampler2D atlas, vec2 uv, vec4 nativeSample, ivec2 phase, bool filteredCoverage, bool rgss) {
    ChromaMaterial material;
    material.color = nativeSample;
    material.tangentNormal = vec3(0.0, 0.0, 1.0);
    material.mapped = false;
    ivec2 pixel = ivec2(floor(uv * vec2(textureSize(atlas, 0))));
    ivec2 origin = pixel - ((pixel - phase) & ivec2(3));
    int code;
    float coverage;
    vec2 dx = dFdx(uv * vec2(textureSize(atlas, 0)));
    vec2 dy = dFdy(uv * vec2(textureSize(atlas, 0)));
    float footprint = rgss ? min(dot(dx, dx), dot(dy, dy)) : max(dot(dx, dx), dot(dy, dy));
    float lod = 0.5 * log2(max(footprint, 0.0001));
    bool minified = filteredCoverage && lod >= 1.0 && textureSize(atlas, 1).x > 0;
    if (chromaReadNormalTile(atlas, origin, code, coverage)) {
        material.mapped = true;
        // Subpixel relief fades toward the geometric normal instead of aliasing
        // between unrelated source texels at long distances or grazing angles.
        float detail = 1.0 - smoothstep(4.0, 16.0, sqrt(max(dot(dx, dx), dot(dy, dy))));
        material.tangentNormal = normalize(vec3((vec2(code % 15, code / 15) - 7.0) / 7.0 * detail, 1.0));
        // Below mip 1 the texture alpha is metadata. Above it the mean alpha
        // is real cutout coverage scaled by 191/255.
        material.color.a = minified ? chromaMipCoverage(atlas, uv, lod, coverage) : coverage;
    } else if (textureSize(atlas, 2).x == 0 && nativeSample.a < 1.0 &&
            chromaNormalHoleCandidate(atlas, pixel)) {
        // A fractional model UV can hide the sprite's exact phase at mip 0/1.
        // Search only to restore coverage: this code is not self-synchronizing,
        // so a second matching phase must never supply a surface normal.
        // Opaque native mob pixels skip this bounded fallback completely.
        bool foundCoverage = false;
        for (int y = 0; y < 4 && !foundCoverage; ++y) {
            for (int x = 0; x < 4; ++x) {
                ivec2 candidate = pixel - ivec2(x, y);
                if (all(equal(candidate, origin))) continue;
                if (chromaReadNormalTile(atlas, candidate, code, coverage)) {
                    material.color.a = minified ? chromaMipCoverage(atlas, uv, lod, coverage) : coverage;
                    foundCoverage = true;
                    break;
                }
            }
        }
    } else if (minified && nativeSample.a > 0.0 && nativeSample.a < 191.5 / 255.0 &&
            texelFetch(atlas, pixel, 0).a == 0.0) {
        // A cutout hole has no payload. Its mip can nevertheless contain some
        // neighbouring material. Validate a neighbouring prepared cell before
        // restoring that coverage; never rescale an ordinary translucent texel.
        for (int side = 0; side < 4; ++side) {
            ivec2 offset = side == 0 ? ivec2(4, 0) : side == 1 ? ivec2(-4, 0) :
                           side == 2 ? ivec2(0, 4) : ivec2(0, -4);
            if (chromaReadNormalTile(atlas, origin + offset, code, coverage)) {
                material.color.a = chromaMipCoverage(atlas, uv, lod, 0.0);
                break;
            }
        }
    }
    return material;
}

// Item/entity/GUI samplers can clamp to mip zero even when the atlas allocates
// other levels. Their binary coverage comes from the decoded original texel.
ChromaMaterial chromaSampleMaterial(sampler2D atlas, vec2 uv, vec4 nativeSample) {
    return chromaSampleMaterial(atlas, uv, nativeSample, ivec2(0), false, false);
}

ChromaMaterial chromaSampleMaterial(sampler2D atlas, vec2 uv, vec4 nativeSample, ivec2 phase) {
    return chromaSampleMaterial(atlas, uv, nativeSample, phase, false, false);
}

ChromaMaterial chromaSampleMaterial(sampler2D atlas, vec2 uv, vec4 nativeSample, bool filteredCoverage, bool rgss) {
    return chromaSampleMaterial(atlas, uv, nativeSample, ivec2(0), filteredCoverage, rgss);
}

ChromaMaterial chromaSampleTerrainMaterial(sampler2D atlas, vec2 uv, vec4 nativeSample, bool rgss) {
    return chromaSampleMaterial(atlas, uv, nativeSample, ivec2(0), true, rgss);
}

ChromaMaterial chromaSampleTerrainMaterial(sampler2D atlas, vec2 uv, vec4 nativeSample, ivec2 phase, bool rgss) {
    return chromaSampleMaterial(atlas, uv, nativeSample, phase, true, rgss);
}

float chromaMaterialAlpha(ChromaMaterial material, vec3 eyePosition, vec2 uv, mat3 eyeToWorld) {
#if CHROMA_NORMAL_MAPS
    if (material.mapped) {
        vec3 dpdx = dFdx(eyePosition), dpdy = dFdy(eyePosition);
        vec2 duvdx = dFdx(uv), duvdy = dFdy(uv);
        float determinant = duvdx.x * duvdy.y - duvdx.y * duvdy.x;
        vec3 crossed = cross(dpdx, dpdy);
        if (abs(determinant) > 1e-16 && dot(crossed, crossed) > 1e-20) {
            vec3 n = normalize(crossed);
            if (dot(n, eyePosition) > 0.0) n = -n;
            vec3 t = (dpdx * duvdy.y - dpdy * duvdx.y) / determinant;
            vec3 b = (dpdy * duvdx.x - dpdx * duvdy.x) / determinant;
            t = normalize(t - n * dot(t, n));
            b = normalize(b - n * dot(b, n) - t * dot(b, t));
            // OpenGL normal maps have +Y up; texture V increases downwards.
            vec3 detail = normalize(t * material.tangentNormal.x - b * material.tangentNormal.y + n * material.tangentNormal.z);
            return chromaEncodeMaterialNormal(normalize(eyeToWorld * n), normalize(eyeToWorld * detail));
        }
    }
#endif
    return 1.0;
}
#endif
