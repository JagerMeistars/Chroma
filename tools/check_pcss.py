"""CPU mathematics/source contracts for Dynamic hybrid radial-depth PCSS. No GPU.

Run: python tools/check_pcss.py
Analytic planes/half-planes generate depths independently of the surfel cache.
This is a double-precision reference, not GLSL execution, visual QA or an FPS test.
"""
from pathlib import Path
import math
import json
import random
import re

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / 'assets/chroma/shaders/include/shadow_filter.glsl').read_text()
CONFIG = (ROOT / 'assets/chroma/shaders/include/shadow_config.glsl').read_text()
RES = 128
SAMPLES = 16
MAX_SLOPE = 1.0
MAX_BIAS = .05


def add(a, b): return tuple(x + y for x, y in zip(a, b))
def sub(a, b): return tuple(x - y for x, y in zip(a, b))
def mul(a, s): return tuple(x * s for x in a)
def dot(a, b): return sum(x * y for x, y in zip(a, b))
def cross(a, b): return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])
def length(v): return math.sqrt(dot(v, v))
def unit(v): return mul(v, 1 / length(v))
def sign(x): return -1. if x < 0 else 1.


def disk(count):
    # Independent golden-angle construction; also checks the GLSL constants.
    return [(math.sqrt((i+.5)/count)*math.cos(i*2.399963229728653),
             math.sqrt((i+.5)/count)*math.sin(i*2.399963229728653)) for i in range(count)]


SEARCH = [(0., 0.)] + [(math.sqrt(i/8)*math.cos(i*2.399963229728653),
                        math.sqrt(i/8)*math.sin(i*2.399963229728653)) for i in range(1, 9)]
NEAR = [(0, 0), (-1, 0), (1, 0), (0, -1), (0, 1),
        (-1, -1), (1, -1), (-1, 1), (1, 1)]


def uv(ray):
    x, y, z = mul(ray, 1 / sum(abs(x) for x in ray))
    if z < 0: x, y = (1-abs(y))*sign(x), (1-abs(x))*sign(y)
    return ((x+1)*.5, (y+1)*.5)


def fold(pixel):
    x, y = pixel
    if x < 0: x, y = -x-1, RES-1-y
    if x >= RES: x, y = 2*RES-1-x, RES-1-y
    if y < 0: x, y = RES-1-x, -y-1
    if y >= RES: x, y = RES-1-x, 2*RES-1-y
    assert 0 <= x < RES and 0 <= y < RES
    return x, y


def ray_at(pixel):
    x, y = ((v+.5)/RES*2-1 for v in fold(pixel))
    z = 1-abs(x)-abs(y)
    if z < 0: x, y = (1-abs(y))*sign(x), (1-abs(x))*sign(y)
    return unit((x, y, z))


def plane_depth(ray, normal, plane):
    denominator = dot(ray, normal)
    return plane/denominator if abs(denominator) >= 1e-5 and denominator*plane > 0 else None


def bias(ray, normal, allowance, target):
    return min(allowance/max(abs(dot(ray, normal)), 1e-5), MAX_BIAS, target*.5)


def has_blocker(depth, radius):
    return 0 <= depth < radius-.001


def bilinear(ray, evaluate):
    p = tuple(v*RES-.5 for v in uv(ray))
    base = tuple(math.floor(v) for v in p)
    f = tuple(v-b for v, b in zip(p, base))
    visible, supported = 0., 0.
    for x, y in ((0, 0), (1, 0), (0, 1), (1, 1)):
        weight = (f[0] if x else 1-f[0]) * (f[1] if y else 1-f[1])
        if weight <= 0: continue
        value = evaluate(ray_at((base[0]+x, base[1]+y)))
        if value is not None:
            visible += weight*value
            supported += weight
    return visible, supported


def normalized(pair):
    return min(1., max(0., pair[0]/pair[1])) if pair[1] > 1e-6 else 1.


def filter_slope(source_radius, receiver_distance, blocker_distance):
    return min(source_radius*max(receiver_distance-blocker_distance, 0)
               / max(receiver_distance*blocker_distance, .0001), MAX_SLOPE)


def basis(axis):
    if axis[2] < -.9999999: tangent = unit((0., -axis[2], axis[1]))
    else:
        a = 1/(1+axis[2])
        tangent = unit((1-axis[0]*axis[0]*a, -axis[0]*axis[1]*a, -axis[0]))
    return tangent, cross(axis, tangent)


def texel_slope(axis):
    sx, sy = sign(axis[0]), sign(axis[1])
    dx, dy = (1., 0., -sx), (0., 1., -sy)
    if axis[2] < 0: dx, dy = (0., -sx*sy, -sx), (-sx*sy, 0., -sy)
    return min(length(sub(d, mul(axis, dot(axis, d)))) for d in (dx, dy))*sum(abs(v) for v in axis)*2/RES


def hybrid_weight(slope, width):
    t = max(0., min(1., (slope-.5*width)/(.5*width)))
    return t*t*(3-2*t)


def pcss(depth_at, receiver, normal, light=(0., 0., 0.), radius=14., source_radius=.35,
         samples=None, hard_at=None, frame=basis):
    """Reference filter; inputs use the same already-canonical map origin."""
    if samples is None: samples = SAMPLES
    if not math.isfinite(radius) or radius <= 0: return 1.
    delta = sub(receiver, light)
    distance, nlength = length(delta), length(normal)
    if not math.isfinite(distance+nlength) or distance <= 1e-5 or nlength <= 1e-4: return 1.
    normal = mul(normal, 1/nlength)
    plane = dot(delta, normal)
    height = -plane
    if height <= 1e-6: return 1.
    allowance = min(.005 if max(abs(x) for x in normal) > .99999 else .035, height*.5)
    axis = mul(delta, 1/distance)
    center = tuple(math.floor(v*RES) for v in uv(axis))
    center_depth = depth_at(ray_at(center))
    if 0 <= center_depth <= .0001: return 0.

    def comparison(ray):
        target = plane_depth(ray, normal, plane)
        if target is None: return None
        depth = depth_at(ray)
        return float(not (has_blocker(depth, radius) and depth < target-bias(ray, normal, allowance, target)))

    def hard():
        return hard_at(receiver, normal, light, allowance, radius, source_radius) if hard_at else normalized(bilinear(axis, comparison))
    if source_radius <= 1e-6: return hard()
    tangent, bitangent = frame(axis)
    angle = min(source_radius/max(.5, distance*.2), MAX_SLOPE)
    depth_sum, count = 0., 0.
    for i, offset in enumerate(SEARCH):
        direction = unit(add(axis, mul(add(mul(tangent, offset[0]), mul(bitangent, offset[1])), angle)))
        p = tuple(v*RES-.5 for v in uv(direction))
        middle = tuple(math.floor(v+.5) for v in p)
        normalization = tuple(2.5-abs(v-m) for v, m in zip(p, middle))
        for offset in (NEAR if i == 0 else [(0, 0)]):
            pixel = tuple(m+o for m, o in zip(middle, offset))
            weight = math.prod(max(1.5-abs(v-q), 0)/n for v, q, n in zip(pixel, p, normalization)) if i == 0 else 1.
            if weight <= 0: continue
            ray = ray_at(pixel)
            target = plane_depth(ray, normal, plane)
            if target is None: continue
            depth = depth_at(ray)
            if not has_blocker(depth, radius) or depth >= target-bias(ray, normal, allowance, target): continue
            axial = depth*dot(ray, axis)
            if not .0001 < axial < distance: continue
            depth_sum += axial*weight
            count += weight
    if count <= 1e-6: return hard()
    angle = filter_slope(source_radius, distance, depth_sum/count)
    weight = hybrid_weight(angle, texel_slope(axis)) if hard_at else 1.
    hard_value = hard() if weight < 1 else 1.
    if weight <= 0: return hard_value
    if angle <= 1e-6: return hard()
    total = (0., 0.)
    for x, y in disk(samples):
        offset = add(mul(tangent, x), mul(bitangent, y))
        if dot(sub(add(light, mul(offset, source_radius)), receiver), normal) <= 0: continue
        direction = unit(add(axis, mul(offset, angle)))
        total = add(total, bilinear(direction, comparison))
    return hard_value*(1-weight) + normalized(total)*weight


def analytic_map(light, planes, radius=14.):
    """Nearest two-sided plane intersection, optionally clipped by a predicate.

    Plane geometry is independent of the voxel encoding, mask and filter.
    """
    def depth(ray):
        closest = radius
        for point, normal, covered in planes:
            denominator = dot(normal, ray)
            if abs(denominator) < 1e-12: continue
            t = dot(normal, sub(point, light))/denominator
            if 0 <= t < closest and covered(add(light, mul(ray, t))): closest = t
        return closest
    return depth


def source_contracts():
    assert '#if CHROMA_STATIC_WORLD\n#include <chroma:shadow_filter_static.glsl>' in SOURCE
    assert 'uniform sampler2D ShadowSampler;' in SOURCE
    for required in ('SurfaceSampler', 'VoxelSampler', 'VoxelLod1Sampler', 'chromaAreaProjectedBlocked', 'chromaPcssHardShadow'):
        assert required in SOURCE, required
    assert 'abs(axis.y) < 0.9' not in SOURCE
    assert 'smoothstep(0.5 * texelSlope, texelSlope, filterAngle)' in SOURCE
    for required in ('light = chromaShadowMapOrigin(light);', 'plane / denominator',
                     'depth < receiverDepth - bias', 'depth * dot(ray, axis)',
                     'for (int i = 0; i < CHROMA_SHADOW_SAMPLES; ++i)',
                     'dot(light + sourceOffset - receiver, normal) <= 0.0',
                     'CHROMA_PCSS_MAX_RADIAL_BIAS = 0.05', 'CHROMA_PCSS_MAX_SLOPE = 1.0'):
        assert required in SOURCE, required
    assert re.search(r'#define CHROMA_SHADOW_SAMPLES\s+16\b', CONFIG)
    arrays = re.findall(r'const vec2 CHROMA_SOURCE_DISK\[(\d+)\] = vec2\[\d+\]\((.*?)\);', SOURCE, re.S)
    for count, block in arrays:
        stored = [tuple(map(float, xy)) for xy in re.findall(r'vec2\(([-.\d]+), ([-.\d]+)\)', block)]
        expected = disk(int(count))
        assert len(stored) == len(expected) and max(length(sub(a, b)) for a, b in zip(stored, expected)) < 1e-8
    # Dynamic atlas/bindings are restored; Static keeps its old wrapper.
    chain = json.loads((ROOT/'assets/minecraft/post_effect/end_of_frame.json').read_text())
    assert chain['targets']['shadow_surface']['persistent']
    passes = chain['passes']
    atlas = next(p for p in passes if p['fragment_shader'] == 'chroma:post/shadow_surface')
    shade_pass = next(p for p in passes if p['fragment_shader'] == 'chroma:post/shade')
    assert passes.index(atlas) < passes.index(shade_pass)
    names = {i['sampler_name'] for i in shade_pass['inputs']}
    assert {'Surface', 'Shadow', 'Voxel', 'VoxelLod1'} <= names
    producer = (ROOT/'assets/chroma/shaders/post/shadow_surface.fsh').read_text()
    for token in ('0x3fffffffu', '0x40000000u', '0x80000000u', 'chromaShadowMapOrigin'):
        assert token in producer, token
    hard_source = SOURCE.split('float chromaPcssHardShadow(', 1)[1].split('float chromaPcssReceiverDepth(', 1)[0]
    assert 'CHROMA_SHADOW_SAMPLES' not in hard_source
    assert 'seedCount < 4' in hard_source and '(i == 0 ? 9 : 1)' in hard_source
    shade = (ROOT / 'assets/chroma/shaders/post/shade.fsh').read_text()
    assert 'chromaShadowReceiver(worldReceiver, worldNormal)' in shade
    assert 'chromaShadow(k, worldReceiver,' in shade


def check_seams():
    # Every possible one-texel border query, including all four folded corners.
    for x in range(-1, RES+1):
        for y in (-1, 0, RES-1, RES):
            assert abs(length(ray_at((x, y)))-1) < 1e-12
    for y in range(-1, RES+1):
        for x in (-1, 0, RES-1, RES): ray_at((x, y))
    rng = random.Random(263)
    for _ in range(1000):
        direction = unit(tuple(rng.uniform(-1, 1) for _ in range(3)))
        pixel = tuple(math.floor(v*RES) for v in uv(direction))
        assert length(sub(direction, ray_at(pixel))) < 5.12 / RES
    # A continuous sphere function must remain continuous at octahedral seams;
    # this expected function does not know the texture folding implementation.
    value = lambda ray: .5 + dot(ray, (.1, -.2, .15))
    for base in ((0., .4, -1.), (.4, 0., -1.), (0., 0., -1.)):
        for axis in (0, 1):
            a, b = list(base), list(base)
            a[axis] -= 1e-7; b[axis] += 1e-7
            assert abs(normalized(bilinear(unit(a), value))-normalized(bilinear(unit(b), value))) < 1e-5


def check_quality_layout():
    # Check all 128 lamp tiles, including every seam query, against the producer
    # and consumer addressing. Low quality must never alias the unused atlas.
    assert '#define CHROMA_SHADOWS_ENABLED 1' in CONFIG
    assert '#define CHROMA_SHADOW_QUALITY 2' in CONFIG
    for quality, size, taps in ((1, 64, 8), (2, 128, 16)):
        assert re.search(rf'#(?:if|elif) CHROMA_SHADOW_QUALITY == {quality}\s+'
                         rf'#define CHROMA_SHADOW_MAP_SIZE {size}\s+'
                         rf'#define CHROMA_SHADOW_SAMPLES {taps}', CONFIG)
    for shader in ('shadow_map', 'shadow_surface'):
        producer = (ROOT/f'assets/chroma/shaders/post/{shader}.fsh').read_text()
        assert 'if (any(greaterThanEqual(pixel, ivec2(16, 8) * CHROMA_SHADOW_MAP_SIZE))) discard;' in producer
        assert 'pixel.x / CHROMA_SHADOW_MAP_SIZE + (pixel.y / CHROMA_SHADOW_MAP_SIZE) * 16' in producer
        assert 'pixel & ivec2(CHROMA_SHADOW_MAP_SIZE - 1)' in producer
        assert '/ float(CHROMA_SHADOW_MAP_SIZE)' in producer
    for shader in ('shadow_filter', 'shadow_filter_static'):
        consumer = (ROOT/f'assets/chroma/shaders/include/{shader}.glsl').read_text()
        assert 'const int CHROMA_SHADOW_RES = CHROMA_SHADOW_MAP_SIZE;' in consumer
        assert 'ivec2(lamp % 16, lamp / 16) * CHROMA_SHADOW_RES' in consumer
        assert 'i < CHROMA_SHADOW_SAMPLES' in consumer
    for lamp in range(128):
        tile = lamp % 16 * RES, lamp // 16 * RES
        for edge in range(-1, RES+1):
            for pixel in ((edge, -1), (edge, RES), (-1, edge), (RES, edge)):
                local = fold(pixel)
                absolute = tuple(a+b for a, b in zip(tile, local))
                assert 0 <= absolute[0] < 16*RES and 0 <= absolute[1] < 8*RES
                assert absolute[0]//RES + absolute[1]//RES*16 == lamp
                assert tuple(v & (RES-1) for v in absolute) == local
    # Without the active-extent guard, this unused texel aliases lamp 16.
    if RES < 128:
        assert (16*RES)//RES == 16 and 16*RES < 2048


def check_planes():
    rng = random.Random(1716)
    naive_false_blocks = 0
    cases = [((0., 0., z), (0., 0., -1. if z > 0 else 1.)) for z in (2., 7., -2., -7.)]
    for _ in range(48):
        point = mul(unit(tuple(rng.uniform(-1, 1) for _ in range(3))), rng.uniform(1, 9))
        tangent = unit(cross(unit(point), (0., 1., 0.) if abs(unit(point)[1]) < .9 else (1., 0., 0.)))
        normal = unit(add(mul(unit(point), -1.), mul(tangent, rng.uniform(-1.5, 1.5))))
        cases.append((point, normal))
    for point, normal in cases:
        depth = analytic_map((0., 0., 0.), [(point, normal, lambda p: True)])
        assert abs(pcss(depth, point, normal)-1) < 1e-12, (point, normal)
        assert abs(pcss(depth, point, normal, source_radius=0)-1) < 1e-12
        blocker = mul(point, .5)
        blocked = analytic_map((0., 0., 0.), [(point, normal, lambda p: True), (blocker, normal, lambda p: True)])
        assert pcss(blocked, point, normal) < 1e-12
        axis = unit(point); center = tuple(math.floor(v*RES) for v in uv(axis))
        for offset in NEAR:
            ray = ray_at(tuple(x+y for x, y in zip(center, offset)))
            actual = depth(ray)
            if actual < length(point)-.005: naive_false_blocks += 1
            expected = plane_depth(ray, normal, dot(point, normal))
            if expected is not None:
                assert abs(dot(sub(mul(ray, expected), point), normal)) < 1e-10
    assert naive_false_blocks > 0, 'Fixtures must expose wrong central-distance comparisons'
    return len(cases), naive_false_blocks


def check_contact_and_limits():
    # Independent similar-triangle construction: extend a ray from the rim of
    # the emitter through a blocker edge to a farther parallel receiver plane.
    for radius in (0., .001, .35, 1.):
        for db, dr in ((2., 2.), (2., 4.), (2., 10.), (.5, 1.)):
            source = (radius, 0., 0.); edge = (0., 0., db)
            rim_hit = add(source, mul(sub(edge, source), dr/db))
            assert abs(filter_slope(radius, dr, db)-min(abs(rim_hit[0])/dr, MAX_SLOPE)) < 1e-12
    assert filter_slope(.35, 4., 3.99) < filter_slope(.35, 4., 2.) < filter_slope(.35, 4., .5)
    assert filter_slope(.35, 4., 1e-12) == MAX_SLOPE
    receiver, normal = (0., 0., 6.), (0., 0., -1.)
    for value in (14., float('inf'), float('nan'), -1.):
        assert pcss(lambda ray: value, receiver, normal) == 1.
    for value in (0., .000025):
        for emitter in (0., .35): assert pcss(lambda ray: value, receiver, normal, source_radius=emitter) == 0.
    assert pcss(lambda ray: 1., receiver, normal, radius=0.) == 1.
    assert pcss(lambda ray: 1., (0., 0., 0.), normal) == 1.
    assert pcss(lambda ray: 1., receiver, (0., 0., 0.)) == 1.
    # An intersection on the wrong receiver hemisphere must not contribute a
    # dark comparison; a disk straddling that hemisphere stays normalized.
    assert plane_depth((0., 0., -1.), normal, -6.) is None
    grazing = unit((1., 0., -.0025))
    admitted = sum(dot(add((0., 0., -4.), (x*.35, y*.35, 0.)), grazing) > 0 for x, y in disk(16))
    assert 0 < admitted < 16
    for depth in (lambda ray: 1., lambda ray: 14.):
        v = pcss(depth, (0., 0., 4.), grazing)
        assert math.isfinite(v) and 0 <= v <= 1
    for cosine in (1., .1, .001, 0.):
        n = unit((math.sqrt(1-cosine*cosine), 0., cosine))
        assert 0 <= bias((0., 0., 1.), n, .035, 5.) <= MAX_BIAS


def check_edge_and_origins():
    light = (0., 0., 0.); normal = (0., 0., -1.)
    floor = ((0., 0., 6.), normal, lambda p: True)
    half = ((0., 0., 2.), normal, lambda p: p[0] <= 0)
    depth = analytic_map(light, [floor, half])
    hard = [pcss(depth, (x, 0., 6.), normal, source_radius=0.) for x in (-1., 0., 1.)]
    soft = [pcss(depth, (x, 0., 6.), normal) for x in (-1., 0., 1.)]
    assert hard[0] == 0 and hard[-1] == 1 and 0 < soft[1] < 1
    assert soft[0] == 0 and soft[-1] == 1
    # Rebuilt light maps follow source movement; translation of the entire
    # scene leaves visibility invariant. Canonical bins match metadata units.
    def canonical(p): return tuple(math.floor(v*4096+.5)/4096 for v in p)
    assert canonical((.100000, -.100000, 0.)) == canonical((.100001, -.100001, 0.))
    assert canonical((.100000, 0., 0.)) != canonical((.101000, 0., 0.))
    for source in ((.100000, -.100000, 0.), (1.25, .5, -.25), (-2., .125, 1.)):
        source = canonical(source)
        world_map = analytic_map(source, [floor, half])
        result = pcss(world_map, (.15, 0., 6.), normal, source)
        for shift in ((7., -12., 20.), (-100000., 200000., -300000.)):
            moved_planes = [(add(p, shift), n, (lambda hit, fn=covered, off=shift: fn(sub(hit, off)))) for p, n, covered in (floor, half)]
            moved = add(source, shift)
            actual = pcss(analytic_map(moved, moved_planes), add((.15, 0., 6.), shift), normal, moved)
            assert abs(actual-result) < 1e-7
    return hard, soft


def check_basis_continuity():
    receiver = (0., 0., 0.); normal = (math.sqrt(.19), .9, 0.)
    point = (2.090068261630037, 4.315450896732819, 0.)
    blocker_normal = (.4322164216288247, .8924152280299648, .1295531769375031)
    side = (.9514529477043309, 0., -.3077942304604489)
    edge = .14643874204562446
    geometry = [(receiver, normal, lambda p: True),
                (point, blocker_normal, lambda hit: dot(sub(hit, point), side) <= edge)]
    sources = [(2.615234375, y, 0.) for y in (5.399658203125, 5.39990234375)]
    def old_frame(axis):
        t = unit(cross(axis, (0., 1., 0.) if abs(axis[1]) < .9 else (1., 0., 0.)))
        return t, cross(axis, t)
    old = [pcss(analytic_map(light, geometry), receiver, normal, light, frame=old_frame) for light in sources]
    new = [pcss(analytic_map(light, geometry), receiver, normal, light) for light in sources]
    assert abs(old[0]-.0625) < 1e-10 and abs(old[1]-.19523449264806797) < 1e-10, old
    assert abs(new[1]-new[0]) < .001, new
    rng = random.Random(1081)
    for _ in range(1000):
        n = unit(tuple(rng.uniform(-1, 1) for _ in range(3)))
        t, b = basis(n)
        assert max(abs(dot(n,t)), abs(dot(n,b)), abs(dot(t,b)), abs(length(t)-1), abs(length(b)-1)) < 1e-10
        assert 0 < texel_slope(n) < .06
        if n[2] > -.99:
            other = basis(unit(add(n, (1e-7, -1e-7, 1e-7))))
            assert max(length(sub(a,b)) for a,b in zip((t,b),other)) < 1e-4
    for n in ((0., 0., -1.), (1e-5, 0., -1.), (0., 1e-5, -1.)):
        assert all(math.isfinite(v) for vector in basis(unit(n)) for v in vector)
    return old, new


def check_hard_geometry():
    # Actual encoded finite masks drive the CPU candidate path. An independent
    # triangulation of every occupied patch supplies the central-ray oracle.
    import check_surfel_voxels as surf
    def cell(p): return tuple(math.floor(v/.25) for v in p)
    def cache_map(cache, light, radius):
        def sample(ray):
            best, guide = radius, None
            for q, records in cache.items():
                hit = surf.ray_hit(records, q, light, ray, best)
                if hit is None: continue
                best = hit
                if any(w & surf.OVERFLOW for w in records): guide = (q, surf.OVERFLOW)
                else:
                    guide = next((q,w) for w in records if surf.ray_hit((w,),q,light,ray,best+.000001) is not None)
            return best, guide
        return sample
    def hard(cache):
        def trace(receiver, normal, light, allowance, radius, source_radius):
            target = add(receiver, mul(normal, allowance)); segment = sub(target, light)
            distance = length(segment)
            if distance <= .00001: return 1.
            axis = unit(segment); tangent, bitangent = basis(axis)
            sample = cache_map(cache, light, radius); seeds = []
            angle = min(source_radius/max(.5,distance*.2), MAX_SLOPE)
            for i, offset in enumerate(SEARCH):
                direction = unit(add(axis, mul(add(mul(tangent,offset[0]),mul(bitangent,offset[1])),angle)))
                middle = tuple(math.floor(v*RES) for v in uv(direction))
                for offset in (NEAR if i == 0 else [(0,0)]):
                    ray = ray_at(tuple(a+b for a,b in zip(middle,offset))); depth, guide = sample(ray)
                    if not .0001 < depth < radius-.001 or depth > distance+source_radius or guide is None: continue
                    if dot(sub(add(light,mul(ray,depth+.0001)),receiver),normal) <= 0: continue
                    q,w = guide; n = (0.,0.,0.) if w&surf.OVERFLOW else surf.normal(w)
                    plane = 0. if w&surf.OVERFLOW else dot(n,surf.point(w,q))
                    duplicate = any((w&surf.OVERFLOW and ow&surf.OVERFLOW and q==oq)
                        or (not w&surf.OVERFLOW and not ow&surf.OVERFLOW and abs(dot(n,on))>.99999
                            and abs(plane-(op if dot(n,on)>0 else -op))<.00001)
                        for oq,ow,on,op in seeds)
                    if not duplicate and len(seeds)<4: seeds.append((q,w,n,plane))
            def occupied(q): return surf.ray_any(cache.get(q,()),q,light,axis,distance-.0001)
            if occupied(cell(light)): return 0.
            for q,w,n,plane in seeds:
                if w&surf.OVERFLOW:
                    # Axis-aligned cell faces nominate actual owner cells;
                    # never treat the infinite face itself as solid.
                    for a in range(3):
                        if abs(axis[a])<1e-6: continue
                        for edge in (q[a]*.25,(q[a]+1)*.25):
                            t=(edge-light[a])/axis[a]
                            if 0<t<distance-.0001 and any(occupied(cell(add(light,mul(axis,t+epsilon)))) for epsilon in (-.0001,.0001)):
                                return 0.
                else:
                    denominator=dot(n,axis)
                    if abs(denominator)<1e-7: continue
                    t=(plane-dot(n,light))/denominator
                    if not 0<t<distance-.0001: continue
                    hit=add(light,mul(axis,t)); before=cell(add(light,mul(axis,t-.0001))); after=cell(add(light,mul(axis,t+.0001)))
                    if (q in (before,after) and surf.covered(w,q,hit)) or occupied(before) or occupied(after): return 0.
            return 1.
        return trace
    def oracle(cache, light, receiver, normal, allowance):
        segment=sub(add(receiver,mul(normal,allowance)),light); distance=length(segment); axis=unit(segment)
        for q,records in cache.items():
            if any(w&surf.OVERFLOW for w in records):
                if surf.box_hit(surf.base(q),add(surf.base(q),(.25,)*3),light,axis,distance-.0001) is not None: return 0.
            for w in records:
                if w&surf.OVERFLOW: continue
                if any(surf.triangle_hit(tri,light,axis,distance-.0001) is not None for tri in surf.triangles(w,q)): return 0.
        return 1.
    cache={}; n=(0.,0.,-1.)
    # The tiny central hole lies between all four nearest depth-map rays.
    for x in range(-2,2):
        for y in range(-2,2):
            q=(x,y,32); word=surf.encode((x*.25+.125,y*.25+.125,8.),n,q)
            if q==(0,0,32): word=surf.encode((.125,.125,8.),n,q,65535^1)
            cache[q]=(word,)
    light=(.03125,.03125,0.); receiver=(.03125,.03125,12.)
    sample=cache_map(cache,light,14.); depth=lambda ray:sample(ray)[0]
    legacy=pcss(depth,receiver,n,light,source_radius=.001)
    hybrid=pcss(depth,receiver,n,light,source_radius=.001,hard_at=hard(cache))
    assert legacy < .1 and hybrid==1., (legacy,hybrid)
    checks=0
    for x,y in ((.03125,.03125),(.09375,.03125),(.03125,.09375),(.21875,.21875),(-.21875,-.21875)):
        # Move source and receiver together so the exact hit crosses each mask.
        light=(x,y,0.); receiver=(x,y,12.)
        for radius in (0.,.001):
            actual=hard(cache)(receiver,n,light,.005,14.,radius)
            assert actual==oracle(cache,light,receiver,n,.005), (x,y,actual)
            checks+=1
    # Actual owner-cell fallback must preserve both a continuous wall across
    # seed-cell boundaries and a hole in that actual owner, not in the guide.
    full={q:(surf.encode(surf.point(words[0],q),n,q),) for q,words in cache.items()}
    for world in (cache,full,{(0,0,32):(surf.OVERFLOW,)}):
        for xy in ((.03125,.03125),(.21,.19)):
            light=(*xy,0.); receiver=(*xy,12.)
            assert hard(world)(receiver,n,light,.005,14.,.001)==oracle(world,light,receiver,n,.005)
            checks+=1
    # An inset source intersects its own cell before crossing any cell face.
    q=(0,0,0); inset={q:(surf.encode((.125,.125,.125),n,q),)}
    assert hard(inset)((.125,.125,1.),n,(.125,.125,.03125),.005,14.,0.)==0.
    # A real quantized plane can lie inside the former .05-block early exit.
    # Keep actual source-cell occlusion even for a short .035-block segment.
    near={(0,0,0):(surf.encode((.125,.125,.033),n,(0,0,0)),)}
    near_light=(.125,.125,0.); near_receiver=(.125,.125,.04)
    assert abs(surf.point(near[(0,0,0)][0],(0,0,0))[2]-.031746031746031744)<1e-12
    for emitter_radius in (0.,.001):
        result=hard(near)(near_receiver,n,near_light,.005,14.,emitter_radius)
        assert result==oracle(near,near_light,near_receiver,n,.005)==0.
        checks+=1
    # Hybrid switch itself is continuous even for maximal disagreement.
    width=texel_slope((0.,0.,1.))
    values=[1-hybrid_weight(width*i/400,width) for i in range(401)]
    assert values[0]==1 and values[-1]==0 and all(a>=b for a,b in zip(values,values[1:]))
    assert max(abs(a-b) for a,b in zip(values,values[1:]))<.01
    for edge in (.5*width,width):
        assert abs(hybrid_weight(edge-1e-8,width)-hybrid_weight(edge+1e-8,width))<1e-8
    return checks,legacy,hybrid


def main():
    global RES, SAMPLES
    source_contracts()
    check_quality_layout()
    check_seams()
    planes, naive = check_planes()
    check_contact_and_limits()
    hard, soft = check_edge_and_origins()
    old_basis, new_basis = check_basis_continuity()
    hard_checks, alias, repaired = check_hard_geometry()
    print(f'PASS PCSS CPU: {planes} analytic radial-plane cases; {naive} naive-distance false blocks; '
          f'1000 octahedral directions and folded borders; contact geometry; finite/embedded/zero-radius/hemisphere/bias controls; '
          f'moving origins. Half-plane hard={hard}, soft={soft}.')
    print(f'Hybrid finite-mask checks={hard_checks}; subtexel hole depth-only={alias}, hybrid={repaired}; basis repro old={old_basis}, new={new_basis}; continuous kernel blend.')
    RES, SAMPLES = 64, 8
    check_quality_layout()
    check_seams()
    low_planes, _ = check_planes()
    check_contact_and_limits()
    low_hard, low_soft = check_edge_and_origins()
    print(f'Low quality CPU: 64x64 / 8 taps; 128 lamp tiles and folded seams; {low_planes} analytic planes; '
          f'contact/limits and moving origins; half-plane hard={low_hard}, soft={low_soft}.')
    print('CPU reference/source contracts only; GLSL compilation, live image quality and FPS are not established.')


if __name__ == '__main__':
    main()
