"""CPU depth/geometry regression checks; this does not execute GLSL or a game.

Depth comes from analytic ray/AABB intersections, independently of the cache
rules. Compare observed cells with true solid bounds and the old edge rejection.
"""
from functools import lru_cache
from itertools import product
from pathlib import Path
import math

import numpy as np

CELL = .25
SIZE = np.array([256, 144])
FOCAL = np.array([1 / math.tan(math.radians(35)) / (16 / 9),
                  1 / math.tan(math.radians(35))])


class DepthScene:
    def __init__(self, boxes, camera=(3, 2.5, 4), target=(0, .75, 0)):
        self.boxes = [(np.array(a, dtype=float), np.array(b, dtype=float)) for a, b in boxes]
        self.camera = np.array(camera, dtype=float)
        back = self.camera - target
        back /= np.linalg.norm(back)
        right = np.cross([0, 1, 0], back)
        right /= np.linalg.norm(right)
        self.rotation = np.array([right, np.cross(back, right), back])

    def project(self, eye):
        if eye[2] >= -.05:
            return None
        p = np.floor((eye[:2] / -eye[2] * FOCAL * .5 + .5) * SIZE).astype(int)
        return tuple(p) if np.all(p >= 2) and np.all(p < SIZE - 2) else None

    @lru_cache(maxsize=None)
    def depth_point(self, pixel):
        if pixel is None:
            return None
        if np.any(np.array(pixel) < 2) or np.any(np.array(pixel) >= SIZE - 2):
            return None
        ray_eye = np.r_[((np.array(pixel) + .5) / SIZE * 2 - 1) / FOCAL, -1]
        ray = self.rotation.T @ ray_eye
        distance = math.inf
        for lo, hi in self.boxes:
            parallel = abs(ray) < 1e-12
            if np.any(parallel & ((self.camera < lo) | (self.camera > hi))):
                continue
            divisor = np.where(parallel, 1, ray)
            a, b = (lo - self.camera) / divisor, (hi - self.camera) / divisor
            enter = float(np.max(np.where(parallel, -math.inf, np.minimum(a, b))))
            leave = float(np.min(np.where(parallel, math.inf, np.maximum(a, b))))
            if leave >= max(.05, enter):
                distance = min(distance, enter if enter >= .05 else leave)
        return ray_eye * distance if math.isfinite(distance) else None

    def occupied_oracle(self, voxel):
        lo = np.array(voxel) * CELL
        hi = lo + CELL
        return any(np.all(np.minimum(hi, b) - np.maximum(lo, a) > 1e-8)
                   for a, b in self.boxes)

    def plane_vacant(self, voxel):
        centre = (np.array(voxel) + .5) * CELL
        pixel = self.project(self.rotation @ (centre - self.camera))
        surface = self.depth_point(pixel)
        if surface is None:
            return False
        x, y = pixel
        sides = [self.depth_point(p) for p in ((x-1, y), (x+1, y), (x, y-1), (x, y+1))]
        if any(p is None for p in sides):
            return False
        dz = [abs(p[2] - surface[2]) for p in sides]
        dx = sides[1] - surface if dz[1] < dz[0] else surface - sides[0]
        dy = sides[3] - surface if dz[3] < dz[2] else surface - sides[2]
        n = np.cross(dx, dy)
        if n @ n < 1e-16:
            return False
        n /= np.linalg.norm(n)
        if n @ surface > 0:
            n = -n
        if any(d > 1 or abs((p - surface) @ n) > .01 for d, p in zip(dz, sides)):
            return False
        normal = self.rotation.T @ n
        axis = int(np.argmax(abs(normal)))
        if abs(normal[axis]) > .98:
            normal = np.eye(3)[axis] * np.sign(normal[axis])
        offset = (self.rotation.T @ surface + self.camera - centre) @ normal
        extent = CELL * .5 * sum(abs(normal))
        return offset <= -extent + .001

    def observed(self, voxel, old=False):
        centre = (np.array(voxel) + .5) * CELL
        centre_eye = self.rotation @ (centre - self.camera)
        pixel = self.project(centre_eye)
        surface = self.depth_point(pixel)
        if surface is None or centre_eye[2] > surface[2] + CELL:
            return False
        if abs(centre_eye[2] - surface[2]) > 1:
            return False
        x, y = pixel
        sides = [self.depth_point(p) for p in ((x-1, y), (x+1, y), (x, y-1), (x, y+1))]
        if old and any(p is None for p in sides):
            return False
        delta = [1e20 if p is None else abs(p[2] - surface[2]) for p in sides]
        horizontal = 1 if delta[1] < delta[0] else 0
        vertical = 3 if delta[3] < delta[2] else 2
        if min(delta[:2]) > 1 or min(delta[2:]) > 1:
            return False
        dx = sides[1] - surface if horizontal else surface - sides[0]
        dy = sides[3] - surface if vertical == 3 else surface - sides[2]
        n = np.cross(dx, dy)
        if n @ n < 1e-16:
            return False
        n /= np.linalg.norm(n)
        if n @ surface > 0:
            n = -n
        if old and any(abs((p - surface) @ n) > CELL * .5 for p in sides):
            return False
        normal = self.rotation.T @ n
        axis = int(np.argmax(abs(normal)))
        if abs(normal[axis]) > .98:
            normal = np.eye(3)[axis] * np.sign(normal[axis])
        surface_world = self.rotation.T @ surface + self.camera
        plane_offset = (surface_world - centre) @ normal
        plane_limit = .15 if old else CELL * .5 * np.sum(abs(normal)) + CELL * .08
        if not old and abs(plane_offset) > plane_limit:
            return False
        probe = centre + normal * (CELL * .5 if old else plane_offset)
        hit_eye = self.depth_point(self.project(self.rotation @ (probe - self.camera)))
        if hit_eye is None:
            return False
        hit = self.rotation.T @ hit_eye + self.camera
        if np.linalg.norm(hit - probe) > .15 or abs((hit - centre) @ normal) > plane_limit:
            return False
        hit_cell = np.floor((hit - normal * (CELL * .08)) / CELL).astype(int)
        return hit_cell[axis] == voxel[axis] if old else np.array_equal(hit_cell, voxel)


def footprint_vacancy(scene, voxel, bob=None):
    """Geometry reference for the vacancy gate; this does not execute GLSL.

    A background sample at the projected centre says nothing about a partially
    filled cell. Test every raster ray through its projected box instead. A
    nearer occluder or an out-of-view/near-clipped footprint remains unknown.
    Plane contact at the ray's far box boundary is empty, not a retained caster.
    Batched independent ray/AABB depths keep the CPU check small and fast;
    exact_reads counts a row-major implementation's early-exit texture reads.
    """
    low = np.asarray(voxel, dtype=float) * CELL
    high = low + CELL
    corners = np.array([scene.rotation @ (low + np.asarray(o)*CELL - scene.camera)
                        for o in product((0,1), repeat=3)])
    projection = np.array([[FOCAL[0],0,0,0],[0,FOCAL[1],0,0],
                           [0,0,0,.05],[0,0,-1,0]],dtype=float)
    if bob is not None: projection = projection @ bob
    clip = np.column_stack((corners,np.ones(8))) @ projection.T
    ndc = clip[:,:3] / clip[:,3,None]
    if np.any(clip[:,3]<=0) or np.any(ndc[:,2]<=0) or np.any(ndc[:,2]>=1):
        return dict(clear=False, coarse=False, exact_reads=0, reason='clipped/unknown footprint')
    pixels = np.floor((ndc[:,:2]*.5+.5)*SIZE).astype(int)
    first,last = np.min(pixels,axis=0),np.max(pixels,axis=0)
    if np.any(first<2) or np.any(last>=SIZE-2):
        return dict(clear=False, coarse=False, exact_reads=0, reason='clipped/unknown footprint')
    xy = np.array([(x,y) for y in range(first[1],last[1]+1) for x in range(first[0],last[0]+1)])
    inverse = np.linalg.inv(projection)
    def unproject(depth):
        h = np.column_stack(((xy+.5)/SIZE*2-1,np.full(len(xy),depth),np.ones(len(xy)))) @ inverse.T
        return h[:,:3]/h[:,3,None]
    near,far_point = unproject(1.0),unproject(.001)
    starts = near @ scene.rotation + scene.camera
    rays = (far_point-near) @ scene.rotation

    def intervals(a,b):
        parallel = abs(rays)<1e-12
        divisor = np.where(parallel,1,rays)
        t0,t1 = (a-starts)/divisor,(b-starts)/divisor
        enter = np.max(np.where(parallel,-np.inf,np.minimum(t0,t1)),axis=1)
        leave = np.min(np.where(parallel,np.inf,np.maximum(t0,t1)),axis=1)
        outside = np.any(parallel & ((starts<a)|(starts>b)),axis=1)
        return enter,leave,(~outside)&(leave>=np.maximum(0,enter))

    _,far,inside = intervals(low,high)
    depth = np.full(len(xy),np.inf)
    for a,b in scene.boxes:
        enter,leave,visible = intervals(a,b)
        depth = np.minimum(depth,np.where(visible,np.where(enter>=0,enter,leave),np.inf))
    # Simulate the conservative max reversed-depth query, including full P*B.
    # Its global far bound is sufficient, but deliberately not necessary.
    visible = np.isfinite(depth)
    scene_depth = np.zeros(len(xy))
    points = starts[visible]+rays[visible]*depth[visible,None]
    eye = (points-scene.camera) @ scene.rotation.T
    clip = np.column_stack((eye,np.ones(len(eye)))) @ projection.T
    scene_depth[visible] = clip[:,2]/clip[:,3]
    coarse = bool(scene_depth.max() <= ndc[:,2].min())
    contradiction = inside & (depth<far-.001/np.linalg.norm(rays,axis=1))
    contradictions = np.flatnonzero(contradiction)
    reads = int(inside[:contradictions[0]+1].sum()) if len(contradictions) else int(inside.sum())
    return dict(clear=bool(inside.any() and not contradiction.any()),coarse=coarse,
                exact_reads=reads,raster_pixels=len(xy),voxel_pixels=int(inside.sum()),
                contradictions=int(contradiction.sum()),bounds=[first.tolist(),last.tolist()])


def check_footprint_vacancy():
    saved_size = SIZE.copy()
    SIZE[:] = [1920,1080]
    try:
        floor = [((-8,-.25,-8),(8,0,8))]
        fence = [((-.125,0,-.125),(.125,1.5,.125)),
                 ((-.75,.375,-.0625),(.75,.5625,.0625)),
                 ((-.75,.9375,-.0625),(.75,1.125,.0625))]
        voxel = (-3,2,0)
        first = DepthScene(floor+fence,camera=(2.916,2.5,4))
        moved = DepthScene(floor+fence,camera=(2.918,2.5,4))
        assert first.observed(voxel) and first.occupied_oracle(voxel)
        centre = moved.rotation @ ((np.asarray(voxel)+.5)*CELL-moved.camera)
        hit = moved.depth_point(moved.project(centre))
        assert centre[2] > hit[2]+CELL, 'The two-millimetre regression must trigger the old false clear'
        fence_checks = [footprint_vacancy(s,voxel) for s in (first,moved)]
        assert all(not p['clear'] and p['contradictions']>0 for p in fence_checks)
        removed = footprint_vacancy(DepthScene(floor,camera=(2.918,2.5,4)),voxel)
        assert removed['clear'] and removed['coarse']
        # All downward proposals, including an eight-phase observation, need
        # this shared gate. No delayed average or confidence hysteresis is used.
        sequence = [3]
        for scene in (moved,first)*4:
            proposal = 0 if scene is moved else 3
            sequence.append(proposal if proposal>=sequence[-1] or footprint_vacancy(scene,voxel)['clear'] else sequence[-1])
        assert sequence==[3]*9

        floor = [((-12,0,-12),(13,1,13))]
        leg = [((-.25,1,3),(0,2,3.5))]
        pose = dict(camera=(8,8.62,10),target=(3,1,0))
        present,absent = DepthScene(floor+leg,**pose),DepthScene(floor,**pose)
        contact_checks = []
        for cell in ((-1,4,12),(-1,4,13)):
            assert not footprint_vacancy(present,cell)['clear']
            proof = footprint_vacancy(absent,cell)
            assert proof['clear'] and not proof['coarse'], 'A coarse-only gate must fail this contact case'
            contact_checks.append(proof)
        assert not footprint_vacancy(absent,(-1,3,12))['clear'], 'The floor itself must remain occupied'
        # Opaque whole block: present is retained; deleting it exposes enough
        # background to clear its former visible cells, including floor contact.
        block = [((0,1,0),(1,2,1))]
        before,after = DepthScene(floor+block,**pose),DepthScene(floor,**pose)
        cached = [v for v in product(range(4),range(4,8),range(4)) if before.observed(v)]
        assert cached and all(not footprint_vacancy(before,v)['clear'] for v in cached)
        assert all(footprint_vacancy(after,v)['clear'] for v in cached)
        # A foreground blocker makes vacancy unobservable, not proven.
        hidden = DepthScene([((-.25,0,1),(.25,2,1.25))],camera=(0,1,3),target=(0,1,0))
        assert not footprint_vacancy(hidden,(0,3,0))['clear']
        clipped = DepthScene(floor,camera=(.125,1.125,.125),target=(.125,1.125,1))
        assert not footprint_vacancy(clipped,(0,4,0))['clear']
        # P*B contains real view translation/rotation. Compare its full-matrix
        # unprojection with an independently moved/rotated analytic camera.
        # Normalizing one eye point from origin zero is not equivalent.
        for angle in (-.08,.06):
            c,s = math.cos(angle),math.sin(angle)
            transform = np.array([[c,-s,0],[s,c,0],[0,0,1]])
            bob = np.eye(4); bob[:3,:3] = transform; bob[:3,3] = (.08,-.03,.02)
            for scene,cell in ((first,voxel),(moved,voxel),(present,(-1,4,12)),(absent,(-1,4,12))):
                virtual_camera = scene.camera-scene.rotation.T @ transform.T @ bob[:3,3]
                equivalent = DepthScene(scene.boxes,camera=virtual_camera)
                equivalent.rotation = transform @ scene.rotation
                actual = footprint_vacancy(scene,cell,bob)
                expected = footprint_vacancy(equivalent,cell)
                assert actual['clear']==expected['clear']
                assert actual['voxel_pixels']==expected['voxel_pixels']
                assert actual['contradictions']==expected['contradictions']
                assert actual['clear']==(scene is absent)
        return dict(fence_reads=[p['exact_reads'] for p in fence_checks],
                    fence_pixels=fence_checks[1]['raster_pixels'],
                    contact_reads=[p['exact_reads'] for p in contact_checks],
                    removed_block_cells=len(cached),translated_projection_cases=8)
    finally:
        SIZE[:] = saved_size


def check():
    root = Path(__file__).resolve().parents[1]
    source = (root /
              'assets/chroma/shaders/post/voxel_update.fsh').read_text()
    support = (root / 'assets/chroma/shaders/include/depth_support.glsl').read_text()
    assert 'distanceZ[horizontal] > 1.0 || distanceZ[vertical] > 1.0' in support
    assert 'all(equal(hitCell, expectedCell))' in source
    assert 'vec3 probe = centre + normal * planeOffset;' in source
    assert 'if (abs(planeOffset) > planeLimit) return;' in source
    assert 'void observeBox(' in source and 'clearPlane' not in source
    clear = source.index('if (!positive && any(hadPlane)')
    assert source.index('observeBox(chromaVoxCentre(voxel)') < clear < source.index('bool refine = positive || any(hadPlane);')
    assert 'footprintVacant(voxel, cameraProj, cameraInvProj, cameraRot, size)' in source[clear:clear + 250]
    assert 'fragColor = vec4(0.0); return;' in source[clear:clear + 250]
    assert 'clearObservedAir' not in source, 'Surface retention no longer uses coarse eye-depth confidence decay'
    assert 'retained && !updateSlice' in source and 'chromaVoxEncode(records[slot])' in source
    assert 'footprintVacant(voxel, cameraProj, cameraInvProj, cameraRot, size)' in source, 'Overflow full-cell removal still requires volume proof'
    assert 'planePatchVacant(voxel, point, normal, axis, bit, size)' in source, 'Retained surface bits need their plane footprint'
    assert 'mask |= positives;' in source, 'Current surface hits must win over background patch probes'
    assert 'vec3 direction = inverseRotation * (farEye - nearEye);' in source
    assert 'eyeAt(pixel, 1.0, inverseProjection, size)' in source
    assert 'eyeAt(pixel, 0.001, inverseProjection, size)' in source
    assert 'return tested;' in source
    assert 'abs(dot(side[i] - surface, normalEye)) > CHROMA_VOX_CELL * 0.5) return previous;' not in source
    scenes = {
        'slab': [((-.5, 0, -.5), (.5, .5, .5))],
        'stairs': [((-.5, 0, -.5), (.5, .5, .5)), ((-.5, .5, 0), (.5, 1, .5))],
        'fence': [((-.125, 0, -.125), (.125, 1.5, .125)),
                  ((-.75, .375, -.0625), (.75, .5625, .0625)),
                  ((-.75, .9375, -.0625), (.75, 1.125, .0625))],
        # Non-grid-aligned boxes approximate visible head/body/limbs, not an
        # assertion that vanilla entities expose collision shapes to the RP.
        'entity': [((-.28, .5, -.15), (.32, 1.3, .2)),
                   ((-.23, 1.3, -.23), (.27, 1.8, .27)),
                   ((-.25, 0, -.12), (-.05, .5, .15)),
                   ((.1, 0, -.12), (.3, .5, .15))],
    }
    totals = []
    for name, boxes in scenes.items():
        old_count = new_count = 0
        lo = np.floor(np.min([a for a, b in boxes], axis=0) / CELL).astype(int) - 1
        hi = np.ceil(np.max([b for a, b in boxes], axis=0) / CELL).astype(int) + 1
        cells = list(product(*(range(a, b) for a, b in zip(lo, hi))))
        for camera in ((3, 2.5, 4), (-3, 2.5, 4), (3, 2.5, -4)):
            depth = DepthScene(boxes, camera)
            old_cells = {v for v in cells if depth.observed(v, old=True)}
            new_cells = {v for v in cells if depth.observed(v)}
            assert all(depth.occupied_oracle(v) for v in new_cells), (name, camera, 'empty cell marked')
            assert not any(depth.plane_vacant(v) for v in new_cells), (name, camera, 'visible solid cleared')
            old_count += sum(depth.occupied_oracle(v) for v in old_cells)
            new_count += len(new_cells)
        assert new_count >= old_count, (name, old_count, new_count)
        totals.append((name, old_count, new_count))
    assert any(new > old for name, old, new in totals if name == 'fence')
    # Remove a visible, non-grid-aligned actor in front of an analytic floor.
    # Its exposed occupied cells should clear immediately, without eight phases.
    actor = scenes['entity']
    floor = [((-5, -.25, -5), (5, 0, 5))]
    before = DepthScene(actor + floor)
    after = DepthScene(floor)
    cells = product(range(-2, 3), range(0, 8), range(-2, 3))
    cached = [v for v in cells if before.observed(v)]
    clear = 0
    for v in cached:
        eye = after.rotation @ ((np.array(v) + .5) * CELL - after.camera)
        surface = after.depth_point(after.project(eye))
        if surface is None or eye[2] > surface[2] + CELL:
            clear += 1
    assert cached and clear >= len(cached) * .8, (clear, len(cached))
    # Reproduce two confirmed live residual positions at the real view/1920x1080.
    # Before removal a quarter-width leg occupies them. Afterwards their centres
    # lie too close to the floor for the old .25 eye-depth vacancy margin, while
    # the confirmed floor plane touches the empty cells' lower boundary.
    old_size = SIZE.copy()
    SIZE[:] = [1920, 1080]
    try:
        floor = [((-12, 0, -12), (13, 1, 13))]
        leg = [((-.25, 1, 3), (0, 2, 3.5))]
        before = DepthScene(floor + leg, camera=(8, 8.62, 10), target=(3, 1, 0))
        after = DepthScene(floor, camera=(8, 8.62, 10), target=(3, 1, 0))
        for v in [(-1, 4, 12), (-1, 4, 13)]:
            assert before.observed(v) and not before.plane_vacant(v)
            eye = after.rotation @ ((np.array(v) + .5) * CELL - after.camera)
            surface = after.depth_point(after.project(eye))
            assert not (eye[2] > surface[2] + CELL), 'Regression no longer exercises the old failure'
            assert after.plane_vacant(v) and not after.occupied_oracle(v)
        assert not after.plane_vacant((-1, 3, 12)), 'The solid floor cell must remain'
        # A fixed camera sees the floor at the cell-centre pixel, but a tiny
        # caster at the projected plane probe. Analytic depth (not invented
        # confidence inputs) proves both observations coexist in a real scene.
        # The former early clear made this occupied cell oscillate 0/3 forever.
        floor = [((-5, -.25, -5), (5, 0, 5))]
        tiny = [((.05, 0, .05), (.16, .05, .16))]
        pose = dict(camera=(-1, 1.4, -1), target=(.125, .125, .125))
        occupied = DepthScene(floor + tiny, **pose)
        removed = DepthScene(floor, **pose)
        voxel = (0, 0, 0)
        assert occupied.occupied_oracle(voxel)
        assert occupied.observed(voxel) and occupied.plane_vacant(voxel)
        assert not removed.occupied_oracle(voxel) and not removed.observed(voxel)
        assert removed.plane_vacant(voxel)
        def advance(scene, previous, early_clear):
            vacant = previous > 0 and scene.plane_vacant(voxel)
            if early_clear and vacant:
                return 0
            if scene.observed(voxel):
                return 3
            return 0 if vacant else previous
        old_sequence, fixed_sequence = [0], [0]
        for _ in range(6):
            old_sequence.append(advance(occupied, old_sequence[-1], True))
            fixed_sequence.append(advance(occupied, fixed_sequence[-1], False))
        assert old_sequence == [0, 3, 0, 3, 0, 3, 0]
        assert fixed_sequence == [0, 3, 3, 3, 3, 3, 3]
        assert advance(removed, fixed_sequence[-1], False) == 0
    finally:
        SIZE[:] = old_size
    print('PASS: analytic depth scenes; no learned cell outside solid AABBs;', totals)
    print(f'Removed actor: {clear}/{len(cached)} cached surface cells are proven vacant immediately.')
    print('Contact-plane regression: both former leg cells clear; the adjacent solid floor cell remains.')
    print(f'Fixed-view tiny caster: old {old_sequence}; fixed {fixed_sequence}; removal clears to 0.')
    print('Legacy CPU reference checks visible vacancies immediately; current Dynamic updates eight slices and stores masked surfaces. Hidden edits remain limited.')
    print('CPU FOOTPRINT PASS: exact vacancy footprint holds the two-millimetre fence motion, '
          'clears removed fence/block/contact cells and retains hidden/clipped cells;',check_footprint_vacancy())


if __name__ == '__main__':
    check()
