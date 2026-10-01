"""Compare persistent first-LOD skips with a full surface-record reduction. No GPU."""
from pathlib import Path
import json
import random
import re

from build_shadows import configure

ROOT = Path(__file__).resolve().parents[1]
N = 256


def world(storage, origin):
    return tuple(o + ((s - o) & 255) for s, o in zip(storage, origin))


def contains(cell, origin):
    return all(0 <= a - b < N for a, b in zip(cell, origin))


def phase(cell, frame):
    return ((cell[1] ^ (cell[2] >> 3)) % 8) == frame % 8


def records(cell, epoch):
    # Sparse independent data: transparent valid records, real surface masks,
    # and overflow all occur. Dense random words would make every parent full.
    x, y, z = cell
    h = ((x * 73856093) ^ (y * 19349663) ^ (z * 83492791) ^ (epoch * 2654435761)) & 0xffffffff
    data = [0, 0x40000000, 0, 0]
    if h % 29 == 0:
        data[(h >> 5) & 3] = 0x40000000 | (1 << (14 + ((h >> 8) & 15)))
    if h % 173 == 0:
        data[(h >> 13) & 3] = 0x80000000
    return tuple(data)


def reduce_full(data):
    result = 0
    for parent in range(16):
        occupied = any(word & 0x80000000 or word & 0x40000000 and word >> 14 & 65535
                       for child in data[parent * 8:parent * 8 + 8] for word in child)
        if occupied:
            result |= 3 << (2 * parent)
    return result


def check_case(pixel, origin, previous, frame, history=True, camera=True):
    px, py = pixel
    first = ((px % 8) * 32, py * 2, (px // 8) * 2)
    storage = [tuple(a + b for a, b in zip(first,
               (i * 2 + (child & 1), (child >> 1) & 1, child >> 2)))
               for i in range(16) for child in range(8)]
    current_cells = [world(v, origin) for v in storage]
    old_cells = [world(v, previous) for v in storage]
    old_data = [records(cell, 1) for cell in old_cells]
    full_data = []
    changed_children = []
    for cell, old in zip(current_cells, old_data):
        changed = camera and (not history or not contains(cell, previous) or phase(cell, frame))
        changed_children.append(changed)
        full_data.append(records(cell, 2) if changed else old)
    old_word, expected = reduce_full(old_data), reduce_full(full_data)

    first_world = world(first, origin)
    pair_active = phase(first_world, frame) or phase(
        (first_world[0], first_world[1] + 1, first_world[2]), frame)
    discard = not camera or (history and origin == previous and not pair_active)
    if discard:
        # Independent proof over every real wrapped child, not just endpoints.
        assert not any(changed_children)
    actual = old_word if discard else expected
    assert actual == expected
    return discard, old_word != expected


def check():
    source = (ROOT / 'assets/chroma/shaders/post/voxel_lod.fsh').read_text()
    space = (ROOT / 'assets/chroma/shaders/include/voxel_space.glsl').read_text()
    compact = re.sub(r'\s+', ' ', source)
    assert 'int phase = voxel.y ^ (voxel.z >> 3);' in space
    assert 'bool retained = historyValid != 0 && sameWindow;' in compact
    assert 'bool sameWindow = all(equal(origin, previousOrigin));' in compact
    assert 'if (retained && !updateSlice) discard;' in compact
    assert 'if (cameraValid == 0) discard;' in compact
    assert 'firstWorld + ivec3(0, 1, 0)' in compact
    for location, typ, name in ((0, 'int', 'cameraValid'), (12, 'int', 'historyValid'),
                                (13, 'ivec3', 'previousOrigin'), (14, 'uint', 'frame')):
        assert f'layout(location = {location}) flat in {typ} {name};' in source
    chain = configure(json.loads((ROOT / 'assets/minecraft/post_effect/end_of_frame.json').read_text()))
    lod = [p for p in chain['passes'] if p['fragment_shader'] == 'chroma:post/voxel_lod']
    assert len(lod) == 2
    for p in lod:
        assert p['vertex_shader'] == 'chroma:post/voxel_update'
        inputs = {i['sampler_name']: i['target'] for i in p['inputs']}
        assert inputs['MatDec'] == 'matdec' and inputs['Meta'] == 'voxel_meta_history'
        assert chain['targets'][p['output']]['persistent']

    rng = random.Random(263)
    checks = skipped = changed = 0
    origins = [(0, 0, 0), (-132, -260, 4), (4, -4, 252), (252, 256, -252),
               (119999600, -384, -119999600)]
    moves = [(0, 0, 0), (4, 0, 0), (-4, 0, 0), (0, 4, 0), (0, 0, -4),
             (4, -4, 4), (260, 0, 0), (0, -260, 0), (0, 0, 260), (-520, 516, 260)]
    for origin in origins:
        for move in moves:
            previous = tuple(a - b for a, b in zip(origin, move))
            for frame in range(8):
                for pixel in [(0, 0), (7, 127), (8, 0), (1023, 127),
                              (rng.randrange(1024), rng.randrange(128))]:
                    for history, camera in [(True, True), (False, True), (True, False)]:
                        skip, change = check_case(pixel, origin, previous, frame, history, camera)
                        checks += 1; skipped += skip; changed += change
    # An unchanged word has exactly two active phases out of eight, including
    # origins that split its 32 X children across the toroidal window boundary.
    for origin in origins:
        assert sum(check_case((0, 0), origin, origin, f)[0] for f in range(8)) == 6
    assert changed > 100 and skipped > 100
    print(f'PASS: {checks} full-record reductions; {skipped} exact skips; '
          f'{changed} changed outputs; negative/large origins, all-axis shifts, '
          'teleports, X word wrap, invalid history/camera; both LOD bindings')


if __name__ == '__main__':
    check()
