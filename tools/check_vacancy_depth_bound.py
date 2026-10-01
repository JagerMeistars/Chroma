"""Conservative current-frame tile-depth bound, CPU mathematics only.

Run: python tools/check_vacancy_depth_bound.py
Embedded float32 matrices are from the named native captures. This does not
execute GLSL, change the pack, or establish a GPU performance improvement.
During candidate integration only, --math-only omits production source/graph
contracts. The default requires the adopted vacancy passes to be present.
"""
from pathlib import Path
import argparse
import json
import math
import re
import numpy as np

F = np.float32
SKY = F(1e-6)
NEAR = F(.999999)
W_MARGIN = F(.001)
DEPTH_MARGIN = F(1e-7)

# Rows, copied from MatDec column-major words 1..32.
CAPTURED = (
    ('horse-parity-142523-001-original-wide',
     [[.7071594595909119, 0, 0, 0], [0, 1.2571724653244019, 0, 0],
      [0, 0, 2.4414659492322244e-5, .050001222640275955], [0, 0, -1, 0]],
     [[1.414108157157898, 0, 0, 0], [0, .7954358458518982, 0, 0],
      [0, 0, 0, -1], [0, 0, 19.999509811401367, .00048828125]]),
    ('walking-full-104311-7',
     [[.8033298254013062, .0023320813197642565, -1.4179279787640553e-5, -.02227018028497696],
      [-.004145998973399401, 1.4281156063079834, -.008683080784976482, -.11757597327232361],
      [0, 2.968887429233291e-7, 4.882960638497025e-5, .05000244081020355],
      [0, -.006079984363168478, -.9999815225601196, 0]],
     [[1.2448081970214844, -.0020327444653958082, .5496351718902588, 2.683896673261188e-5],
      [.003613700857385993, .7001916170120239, 1.6480432748794556, -.005999509245157242],
      [-2.1971651221974753e-5, -.004257232882082462, -.010020262561738491, -.9999819397926331],
      [-2.0285062658201205e-15, -3.930438873672726e-13, 19.9990234375, .0009765625]]),
)


def threshold(inverse, maximum_corner_w):
    """None means keep the original exact scan; caller retains clip guards."""
    row = np.asarray(inverse, dtype='f4')[3]
    w = F(maximum_corner_w)
    if not np.all(np.isfinite(row)) or not np.isfinite(w) or w <= 0:
        return None
    ax, ay, q, r = row
    spread = abs(ax)+abs(ay)
    # Non-sky native depth is >SKY. An upper denominator bound alone cannot
    # justify taking a reciprocal when the denominator might be nonpositive.
    if q <= 0 or r-spread+q*SKY <= 0:
        return None
    value = F((F(1)/(w+W_MARGIN)-r-spread)/q-DEPTH_MARGIN)
    # In particular, invalid-pixel sentinel1 must never pass this comparison.
    return value if np.isfinite(value) and 0 < value < NEAR else None


def tile_max(depths, evidence):
    if any(not valid or not math.isfinite(float(d)) or d < 0 or d >= NEAR
           for d, valid in zip(depths, evidence)):
        return F(1)
    return F(max(depths, default=1))


def native_w(projection, inverse, uv, depth):
    """Independent old path: unproject, divide, then project and inspect W."""
    clip = np.concatenate((uv, depth[..., None], np.ones(depth.shape+(1,), 'f4')), axis=-1)
    homogeneous = clip@inverse.T
    eye = homogeneous[..., :3]/homogeneous[..., 3:4]
    return (np.concatenate((eye, np.ones(depth.shape+(1,), 'f4')), axis=-1)@projection.T)[..., 3]


def scan(tiles, bound, maximum_w, accelerated):
    """Each tile supplies actual intersection flags; a bounding box isn't one."""
    tested = False
    for depths, evidence, intersects, world_w in tiles:
        if accelerated and tested and bound is not None and tile_max(depths, evidence) < bound:
            continue
        for depth, valid, covered, w in zip(depths, evidence, intersects, world_w):
            if not covered:
                continue
            tested = True
            if not valid or not math.isfinite(float(depth)) or depth >= NEAR:
                return False
            if depth <= SKY:
                continue
            if not w > maximum_w+F(.0001):
                return False
    return tested


def rectangles(first, last, step):
    """Inclusive native-pixel partitions, in the candidate's tile-major order."""
    for ty in range(first[1]//step[1], last[1]//step[1]+1):
        for tx in range(first[0]//step[0], last[0]//step[0]+1):
            lo = (max(first[0], tx*step[0]), max(first[1], ty*step[1]))
            hi = (min(last[0], (tx+1)*step[0]-1), min(last[1], (ty+1)*step[1]-1))
            yield (tx, ty), lo, hi


def check_two_levels(inverse):
    # Traversal itself must partition the old rectangle exactly, even when
    # native dimensions, fine-tile boundaries and coarse parents do not align.
    for width, height in ((3, 3), (17, 9), (256, 256), (1919, 1079), (1920, 1080), (3840, 2160)):
        step = ((width+255)//256, (height+255)//256)
        first = (min(width-1, 37), min(height-1, 23))
        last = (min(width-1, first[0]+137), min(height-1, first[1]+91))
        visited = []
        for _, lo, hi in rectangles(first, last, (step[0]*8, step[1]*8)):
            for _, a, b in rectangles(lo, hi, step):
                visited.extend((x, y) for y in range(a[1], b[1]+1) for x in range(a[0], b[0]+1))
        expected = {(x, y) for y in range(first[1], last[1]+1) for x in range(first[0], last[0]+1)}
        assert len(visited) == len(expected) and set(visited) == expected

    rng = np.random.default_rng(256328)
    q, r = inverse[3, 2:]
    bound = threshold(inverse, 3)
    coarse_skips = fine_skips = exact_tests = cases = 0
    for width, height in ((96, 80), (513, 257)):
        step = ((width+255)//256, (height+255)//256)
        first, last = (2, 2), (width-3, height-3)
        yy, xx = np.indices((height, width))
        for kind in range(8):
            w = np.full((height, width), 4, dtype='f4')
            valid = np.ones((height, width), bool)
            covered = ((xx-first[0])*3 >= yy-first[1]) & ((xx-first[0])*3 <= yy-first[1]+width)
            if kind == 0: covered[:] = False  # No raster centre ever intersects.
            elif kind == 1: covered[:] = True
            elif kind == 2:
                # One real thin blocker, after an earlier confirmed clear area.
                covered[:] = True; w[height//2, width//2] = F(2.99995)
            elif kind == 3:
                covered[:] = True; valid[height//2, width//2] = False
            elif kind == 4:
                # Unknown pixels outside the footprint may stop the summary,
                # but must not change the fine reference's valid outcome.
                valid[~covered] = False
            elif kind == 5:
                covered[:] = False; covered[height-4, width-4] = True
            elif kind == 6:
                covered[:] = rng.random((height, width)) < .1
                w[rng.random((height, width)) < .005] = F(2.9)
            else:
                covered[:] = True; w[:, :width//2] = F(3.00005)
            depths = ((1/w-r)/q).astype('f4')
            summary_input = np.ones((256*step[1], 256*step[0]), 'f4')
            summary_input[:height, :width] = np.where(valid, depths, F(1))
            fine = summary_input.reshape(256, step[1], 256, step[0]).max(axis=(1, 3))
            coarse = fine.reshape(32, 8, 32, 8).max(axis=(1, 3))
            # Independent exact reference, without either traversal or summaries.
            region = (slice(first[1], last[1]+1), slice(first[0], last[0]+1))
            expected = bool(np.any(covered[region]) and np.all(
                ~covered[region] | (valid[region] & (w[region] > F(3.0001)))))

            def evaluate():
                nonlocal coarse_skips, fine_skips, exact_tests
                tested = False
                for parent, lo, hi in rectangles(first, last, (step[0]*8, step[1]*8)):
                    if tested and coarse[parent[1], parent[0]] < bound:
                        coarse_skips += 1; continue
                    for child, a, b in rectangles(lo, hi, step):
                        if tested and fine[child[1], child[0]] < bound:
                            fine_skips += 1; continue
                        for y in range(a[1], b[1]+1):
                            for x in range(a[0], b[0]+1):
                                exact_tests += 1
                                if not covered[y, x]: continue
                                tested = True
                                if not valid[y, x] or not w[y, x] > F(3.0001): return False
                return tested

            assert evaluate() == expected, (width, height, kind)
            cases += 1
    assert coarse_skips > 0 and fine_skips > 0 and exact_tests > 0
    return cases, coarse_skips, fine_skips


def source_contracts():
    root = Path(__file__).resolve().parents[1]
    post = root/'assets/chroma/shaders/post'
    update = (post/'voxel_update.fsh').read_text()
    assert 'float vacancyDepthLimit(' in update, 'Vacancy candidate has not been adopted; use --math-only for preparation'
    fine = (post/'vacancy_depth.fsh').read_text()
    compact = lambda text: re.sub(r'\s+', '', text)
    update_c, fine_c = compact(update), compact(fine)
    # The mathematical bound must never authorize near/HUD/unknown sentinel1.
    for token in ('w.z>0.0', 'w.w-xy+w.z*0.000001>0.0',
                  'farthestW+0.001', 'depthLimit>0.0&&depthLimit<0.999999&&depth<depthLimit'):
        assert token in update_c, token
    assert update_c.count('booltested=false;') == 2
    assert update_c.count('returntested;') == 2
    for token in ('(size+ivec2(255))/256', '!evidencePixel(p,size)',
                  '!(depth>=0.0&&depth<0.999999)',
                  'chromaVoxEncode(floatBitsToUint(1.0))', 'closest=max(closest,depth)'):
        assert token in fine_c, token

    chain = json.loads((root/'assets/minecraft/post_effect/end_of_frame.json').read_text())
    passes = chain['passes']
    def one(fragment):
        found = [p for p in passes if p['fragment_shader'] == 'chroma:post/'+fragment]
        assert len(found) == 1, fragment
        return found[0]
    fine_pass, acquisition = one('vacancy_depth'), one('voxel_update')
    assert chain['targets']['vacancy_depth']['width'] == 256
    assert chain['targets']['vacancy_depth']['height'] == 256
    assert fine_pass['output'] == 'vacancy_depth'
    inputs = {p['sampler_name']: p for p in fine_pass['inputs']}
    assert inputs['InDepth']['target'] == 'minecraft:main' and inputs['InDepth']['use_depth_buffer']
    assert inputs['MainColor']['target'] == 'minecraft:main' and inputs['Catalog']['target'] == 'catalog'
    inputs = {p['sampler_name']: p for p in acquisition['inputs']}
    assert inputs['VacancyDepth']['target'] == 'vacancy_depth'
    assert passes.index(fine_pass) < passes.index(acquisition)

    coarse = 'vacancy_coarse' in chain['targets']
    if coarse:
        coarse_pass = one('vacancy_lod')
        assert chain['targets']['vacancy_coarse']['width'] == 32
        assert chain['targets']['vacancy_coarse']['height'] == 32
        assert coarse_pass['output'] == 'vacancy_coarse'
        assert coarse_pass['inputs'] == [dict(sampler_name='In', target='vacancy_depth')]
        assert inputs['VacancyCoarse']['target'] == 'vacancy_coarse'
        assert passes.index(fine_pass) < passes.index(coarse_pass) < passes.index(acquisition)
        lod_c = compact((post/'vacancy_lod.fsh').read_text())
        for token in ('ivec2(gl_FragCoord.xy)*8', 'y<8', 'x<8', 'closest=max(closest,depth)',
                      'texelFetch(InSampler,first+ivec2(x,y),0)'):
            assert token in lod_c, token
        for sampler in ('VacancyDepthSampler', 'VacancyCoarseSampler'):
            assert update_c.count('if(tested&&vacancyTileClear('+sampler+',') == 2
    else:
        assert 'VacancyCoarseSampler' not in update
        assert update_c.count('if(tested&&vacancyTileClear(') == 2

    # Reconfiguration must not accumulate stale passes, inputs or targets.
    # This invokes only the pure graph builder; no files or packs are written.
    from build_shadows import configure
    dynamic = configure(chain)
    assert configure(dynamic) == dynamic, 'Dynamic graph configuration is not idempotent'
    assert dynamic == chain, 'Saved Dynamic graph does not match its builder'
    static = configure(chain, {'dims': [64, 64, 64]})
    assert configure(static, {'dims': [64, 64, 64]}) == static
    assert not any(name.startswith('vacancy') for name in static['targets'])
    assert not any(p['output'].startswith('vacancy') for p in static['passes'])
    assert not any(i['sampler_name'].startswith('Vacancy') for p in static['passes'] for i in p['inputs'])
    print('PASS adopted source/graph contracts: max-depth/unknown guards, witnessed exact fallback, '
          + ('two-level256/32' if coarse else 'single-level256')
          + ', builder idempotence and Static exclusion.')


def check():
    matrices = [(name, np.array(p, 'f4'), np.array(i, 'f4')) for name, p, i in CAPTURED]
    for sign in (-1, 1):
        inverse = matrices[0][2].copy()
        inverse[3, :2] = (sign*1e-5, -sign*2e-5)
        matrices.append((f'nonzero_xy_{sign}', np.linalg.inv(inverse).astype('f4'), inverse))
    projection, inverse = matrices[0][1:]
    q, r = map(float, inverse[3, 2:])
    depth_at_w = lambda w: F((1/w-r)/q)
    # A smaller reverse depth alone does NOT satisfy the existing .0001 W gap.
    assert depth_at_w(3.00005) < depth_at_w(3)
    assert not 3.00005 > 3+.0001
    assert not depth_at_w(3.00005) < threshold(inverse, 3)

    wrong = inverse.copy()
    wrong[3] = (.001, 0, 20, 0)
    d = F(.00001)
    naive = (1/(3+.001)-.001)/20-1e-7
    assert d < naive and 1/(-.001+20*d) < 0
    assert threshold(wrong, 3) is None, 'Negative inverse-W must retain the old path'
    for w in (0, -1, math.nan, math.inf):
        assert threshold(inverse, w) is None
    for component in range(4):
        for value in (math.nan, math.inf, -math.inf):
            invalid = inverse.copy(); invalid[3, component] = value
            assert threshold(invalid, 3) is None
    for q_bad in (0, -20):
        invalid = inverse.copy(); invalid[3, 2] = q_bad
        assert threshold(invalid, 3) is None
    assert tile_max([.001, .002], [True, False]) == 1
    assert tile_max([.001, math.nan], [True, True]) == 1
    assert tile_max([.001, 1], [True, True]) == 1
    assert tile_max([0, 0], [True, True]) == 0

    rng = np.random.default_rng(9263256)
    accepted = cases = 0
    minimum_gap = math.inf
    for name, p, inv in matrices:
        count = 12000
        far = rng.uniform(.051, 110, count).astype('f4')
        uv = rng.uniform(-1, 1, (count, 4, 2)).astype('f4')
        uv[:4] = [[[-1, -1], [-1, 1], [1, -1], [1, 1]]]*4
        gap = rng.uniform(-.002, .004, (count, 4)).astype('f4')
        gap[count//2:] += F(.01)
        desired_w = np.maximum(far[:, None]+gap, F(.0501))
        ax, ay, q, r = inv[3]
        depths = ((1/desired_w-r-ax*uv[:, :, 0]-ay*uv[:, :, 1])/q).astype('f4')
        bounds = ((1/(far+W_MARGIN)-r-abs(ax)-abs(ay))/q-DEPTH_MARGIN).astype('f4')
        fast = (depths.max(axis=1) < bounds) & (bounds > 0) & (bounds < NEAR)
        fast &= np.all((depths > SKY) & (depths < NEAR), axis=1)
        assert r-abs(ax)-abs(ay)+q*SKY > 0
        actual_w = native_w(p, inv, uv, depths)
        assert not np.any(fast & np.any(actual_w <= far[:, None]+F(.0001), axis=1)), name
        accepted += int(fast.sum()); cases += count
        minimum_gap = min(minimum_gap, float(np.min(actual_w[fast]-far[fast, None])))

    bound = threshold(inverse, 3)
    clear = ([depth_at_w(4)]*8, [True]*8, [True]*8, [4.]*8)
    unseen = ([depth_at_w(4)]*8, [True]*8, [False]*8, [4.]*8)
    sliver = ([depth_at_w(2.9)]+[depth_at_w(4)]*7,
              [True]*8, [True]+[False]*7, [2.9]+[4.]*7)
    unknown = ([depth_at_w(4)]*8, [False]+[True]*7, [True]*8, [4.]*8)
    unknown_outside = ([depth_at_w(4)]*8, [False]+[True]*7, [False]+[True]*7, [4.]*8)
    for tiles, expected in [([unseen], False), ([clear], True), ([clear, sliver], False),
                            ([clear, unknown], False), ([unknown_outside, clear], True)]:
        assert scan(tiles, bound, 3, False) == expected
        assert scan(tiles, bound, 3, True) == expected
    # Critically, an all-clear summary without a single intersecting raster
    # centre never proves a tiny/subpixel retained plane vacant.
    assert tile_max(unseen[0], unseen[1]) < bound
    assert not scan([unseen, unseen], bound, 3, True)
    hierarchy_cases, coarse_skips, fine_skips = check_two_levels(inverse)
    print(f'PASS CPU depth bound: {cases} float32 tiles, {accepted} accepted, no false old-native-W clears; '
          f'minimum accepted W gap={minimum_gap:.9g}. Naive-depth/inverse-W counterexamples, '
          'nonfinite guards, unknown sentinel, thin-strip and tested=false controls pass. '
          f'Two-level partition/independent exact outcomes: {hierarchy_cases} scenes, '
          f'{coarse_skips} coarse/{fine_skips} fine skips. '
          'No GLSL execution or GPU performance claim.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--math-only', action='store_true', help='Preparation only: skip adopted production source/graph contracts')
    args = parser.parse_args()
    check()
    if not args.math_only:
        source_contracts()
