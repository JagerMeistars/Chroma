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
        plane_limit = .15 if old else CELL * .5 * np.sum(abs(normal)) + .02
        if not old and abs(plane_offset) > plane_limit:
            return False
        probe = centre + normal * (CELL * .5 if old else plane_offset)
        hit_eye = self.depth_point(self.project(self.rotation @ (probe - self.camera)))
        if hit_eye is None:
            return False
        hit = self.rotation.T @ hit_eye + self.camera
        if np.linalg.norm(hit - probe) > .15 or abs((hit - centre) @ normal) > plane_limit:
            return False
        hit_cell = np.floor((hit - normal * .02) / CELL).astype(int)
        return hit_cell[axis] == voxel[axis] if old else np.array_equal(hit_cell, voxel)


def check():
    source = (Path(__file__).resolve().parents[1] /
              'assets/chroma/shaders/post/voxel_update.fsh').read_text()
    assert 'distanceZ[horizontal] > 1.0 || distanceZ[vertical] > 1.0' in source
    assert 'all(equal(hitCell, voxel))' in source
    assert 'vec3 probe = centre + normal * planeOffset;' in source
    assert 'if (abs(planeOffset) > planeLimit) return previous;' in source
    assert 'previous > 0u && planeOffset <= -cellExtent + 0.001' in source
    assert 'if (clearPlane) return 0u;' in source
    assert 'else if (confidence >= 2u) confidence = clearObservedAir' in source
    assert '(oldWord & 0xAAAAAAAAu) == 0u' in source
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
    finally:
        SIZE[:] = old_size
    print('PASS: analytic depth scenes; no learned cell outside solid AABBs;', totals)
    print(f'Removed actor: {clear}/{len(cached)} cached surface cells are proven vacant immediately.')
    print('Contact-plane regression: both former leg cells clear; the adjacent solid floor cell remains.')
    print('Visible vacancies are checked every frame; hidden edits and sub-quarter-cell detail remain limited.')


if __name__ == '__main__':
    check()
