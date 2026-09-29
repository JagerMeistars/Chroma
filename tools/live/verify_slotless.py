"""Functional real-client audit for automatic Chroma source collection.

Writing/importing this module never talks to the client. Pass --run explicitly.
The separately controlled isolated vanilla client must already have the prototype
loaded, the fixture floor prepared, and an inactive benchmark measurement.
No process attach/launch, input simulation, renderer patch, or shader edit occurs.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import time
import traceback

import numpy as np

from request import request

ROOT = Path(__file__).resolve().parents[2]
SHAPES = ('marker', 'marker_spot_narrow', 'marker_spot', 'marker_spot_wide', 'marker_dome')
LAMP_TAG = 'chroma.demo32'
DUMMY_TAG = 'chroma.slotless.audit.dummy'
EXPECTED_INSTANCE = 'chroma-direct-audit-26.3'


def lamp_command(lamp: dict) -> str:
    """Every lamp uses one of only five primary item models; no numbered model ID."""
    shape = int(lamp['shape'])
    rotation = '[0.7071068f,0f,0f,0.7071068f]' if shape in (1, 2, 3) else '[0f,0f,0f,1f]'
    return (
        f'summon minecraft:item_display {lamp["x"]} {lamp["y"]} {lamp["z"]} '
        '{Tags:["' + LAMP_TAG + '","' + LAMP_TAG + '.' + str(lamp['slot']) + '"],'
        'billboard:"fixed",item_display:"none",view_range:4f,width:0f,height:0f,'
        'item:{id:"minecraft:paper",count:1,components:{'
        '"minecraft:item_model":"chroma:' + SHAPES[shape] + '",'
        '"minecraft:custom_model_data":{colors:[' + str(lamp['rgb']) + ']}}},'
        'transformation:{translation:[0f,0f,0f],left_rotation:' + rotation + ','
        'scale:[4f,0.4f,1f],right_rotation:[0f,0f,0f,1f]}}'
    )


def rgb_bytes(value: int) -> tuple[int, int, int]:
    return tuple((value >> shift) & 255 for shift in (16, 8, 0))


class Audit:
    def __init__(self, api: Path, benchmark: Path, output: Path, prefix: str):
        self.api, self.benchmark, self.output, self.prefix = api.resolve(), benchmark.resolve(), output.resolve(), prefix
        self.command_log: list[dict] = []
        self.sequence = 0

    def live_status(self):
        result = request(self.api, 'status')
        assert result.get('ok'), result
        assert Path(result['gameDirectory']).name == 'minecraft' and Path(result['gameDirectory']).parent.name == EXPECTED_INSTANCE, result
        assert result['levelLoaded'] and not result['paused'], result
        return result

    def forbid_active_benchmark(self):
        if (self.benchmark / 'ready.json').exists():
            result = request(self.benchmark, 'status')
            assert result.get('ok'), result
            assert not result.get('measurement') or result['measurement']['complete'], 'Refusing to change game while benchmark is active'
            assert result['framebufferWidth'] == 1920 and result['framebufferHeight'] == 1080, result
            assert result['screen'].endswith('InputLockScreen'), 'Stable direct-API input lock required'
            return result
        raise RuntimeError('No benchmark agent ready; cannot confirm timed run is inactive or input is locked')

    def commands(self, text: str, *, allow_cleanup_noop: bool = False):
        result = request(self.api, 'commands\n' + text)
        self.command_log.append(result)
        assert result.get('ok'), result
        for row in result['commands']:
            valid = bool(row.get('results')) and all(r.get('success') for r in row['results'])
            if not valid:
                conditional_cleanup = allow_cleanup_noop and row['command'].startswith('execute if entity @e[tag=chroma.') and ' run kill @e[tag=chroma.' in row['command']
                assert conditional_cleanup, row
        return result

    def clear(self, *, dummies=False):
        tags = [DUMMY_TAG] if dummies else [LAMP_TAG]
        for tag in tags:
            self.commands(f'execute if entity @e[tag={tag}] run kill @e[tag={tag}]', allow_cleanup_noop=True)

    def replace(self, lamps: list[dict], delay: float = .65):
        self.clear()
        self.commands('\n'.join(lamp_command(lamp) for lamp in lamps))
        time.sleep(delay)

    def snap(self, label: str, *, pixels=False, keep_image=False):
        self.sequence += 1
        name = f'{self.prefix}-{self.sequence:03d}-{label}'
        result = request(self.api, 'dump\n' + name)
        assert result.get('ok'), result
        folder = self.api / 'captures' / name
        manifest = json.loads((folder / 'manifest.json').read_text())
        targets = {target['file']: target for target in manifest['targets']}
        width, height = (targets['main-color.bin'][axis] for axis in ('width', 'height'))
        assert (width, height) == (1920, 1080), (width, height)
        raw = (folder / 'minecraft_matdec-color.bin').read_bytes()
        out = {'name': name, 'folder': folder, 'width': width, 'height': height,
               'u': np.frombuffer(raw, dtype='<u4'), 'f': np.frombuffer(raw, dtype='<f4'),
               'colors': np.fromfile(folder / 'minecraft_colorcache-color.bin', dtype=np.uint8).reshape(-1, 4),
               'manifest': manifest}
        if pixels:
            out['rgb'] = np.fromfile(folder / 'main-color.bin', dtype=np.uint8).reshape(height, width, 4)[..., :3].astype(np.int16)
        # Only discard large outputs created by this exact call, inside its verified
        # owned capture directory. Preserve all compact GPU caches and the manifest.
        expected_parent = (self.api / 'captures').resolve()
        assert folder.resolve().parent == expected_parent and name.startswith(self.prefix + '-')
        for file in ('main-color.bin', 'main-depth.bin'):
            (folder / file).unlink(missing_ok=True)
        if not keep_image:
            (folder / 'main-color.png').unlink(missing_ok=True)
        return out

    def save_report(self, report: dict):
        self.output.parent.mkdir(parents=True, exist_ok=True)
        self.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        self.output.with_suffix('.commands.json').write_text(json.dumps(self.command_log, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def records(snapshot: dict) -> list[dict]:
    u, f = snapshot['u'], snapshot['f']
    assert len(u) == 640, ('unexpected matrix cache', len(u))
    assert u[0] == 1, 'No current camera header'
    found = []
    for index in range(32):
        base = 128 + 16 * index
        if u[base] != 1:
            assert u[base] == 0, (index, 'invalid valid bit', u[base])
            continue
        assert u[base + 10] == 1, (index, 'not fresh this frame', u[base + 10])
        color = snapshot['colors'][index]
        assert color[3] == 255, (index, 'invalid color alpha', color.tolist())
        found.append({'compact_index': index, 'rgb': tuple(map(int, color[:3])), 'shape': int(u[base + 6]),
                      'eye': f[base + 1:base + 4].astype(float), 'radius': float(f[base + 4]),
                      'intensity': float(f[base + 5]), 'axis': f[base + 7:base + 10].astype(float),
                      'address': int(u[base + 11])})
    assert len({r['address'] for r in found}) == len(found), 'Automatic addresses were duplicated'
    assert all(r['address'] <= u[43] for r in found), ('Address beyond header extent', int(u[43]))
    return found


def verify_sources(snapshot: dict, expected: list[dict], *, duplicate_identical=False):
    found = records(snapshot)
    assert len(found) == len(expected), ('active records', len(found), 'expected', len(expected))
    assert int(snapshot['u'][42]) == len(expected), ('catalog count', int(snapshot['u'][42]), 'expected', len(expected))
    assert Counter(r['rgb'] for r in found) == Counter(rgb_bytes(lamp['rgb']) for lamp in expected), 'Missing or wrong colors'
    rot = snapshot['f'][33:42].reshape(3, 3, order='F').astype(float)
    assert np.max(np.abs(rot @ rot.T - np.eye(3))) < .001, 'Camera rotation is not orthonormal'
    groups = defaultdict(list)
    for rec in found:
        groups[rec['rgb']].append(rec)
    matched, translations = {}, []
    for lamp in expected:
        group = groups[rgb_bytes(lamp['rgb'])]
        rec = group.pop(0)
        assert rec['shape'] == lamp['shape'], (lamp['slot'], 'wrong shape', rec['shape'], lamp['shape'])
        assert abs(rec['radius'] - 4.0) < .004 and abs(rec['intensity'] - .4) < .004, (lamp['slot'], 'scale', rec)
        if lamp['shape'] in (1, 2, 3):
            assert np.dot(rec['axis'], rot[:, 1]) > .999, (lamp['slot'], 'spot axis is not downward')
        world = np.array([lamp['x'], lamp['y'], lamp['z']], dtype=float)
        translations.append(rec['eye'] - rot @ world)
        matched[lamp['slot']] = rec
    translations = np.asarray(translations)
    error = float(np.max(np.abs(translations - np.median(translations, axis=0))))
    assert error < .01, ('sources do not share a camera transform', error)
    if duplicate_identical:
        assert np.max(np.ptp(np.asarray([r['eye'] for r in found]), axis=0)) < .001, 'Identical entities did not decode at the same position'
    return matched, {'count': len(found), 'catalog_count': int(snapshot['u'][42]), 'max_address': int(snapshot['u'][43]),
                     'addresses': sorted(r['address'] for r in found), 'position_error_blocks': error,
                     'capture': str(snapshot['folder'].relative_to(ROOT)),
                     'models': sorted({SHAPES[lamp['shape']] for lamp in expected})}


def unchanged_camera(a: dict, b: dict):
    assert np.max(np.abs(a['f'][1:42] - b['f'][1:42])) < .00001, 'Camera changed during image comparison'


def unchanged_sources(before: dict, after: dict):
    for key, original in before.items():
        if key not in after:
            continue
        current = after[key]
        assert original['rgb'] == current['rgb'] and original['shape'] == current['shape'], (key, 'another source changed')
        for field in ('eye', 'axis'):
            assert np.max(np.abs(original[field] - current[field])) < .001, (key, field, 'another source moved')
        assert abs(original['radius'] - current['radius']) < .001 and abs(original['intensity'] - current['intensity']) < .001


def scene_mask(snapshot: dict):
    mask = np.ones((snapshot['height'], snapshot['width']), dtype=bool)
    mask[-1, :32] = False
    columns = snapshot['width'] // 4
    for rec in records(snapshot):
        x, y = 4 * (rec['address'] % columns), snapshot['height'] - 4 - 3 * (rec['address'] // columns)
        mask[max(0, y - 1):y + 2, x:x + 4] = False
    return mask


def floor_geometry(snapshot: dict, first_lamp: dict, first_record: dict):
    """Intersect real inverse-projection rays with known top surface y=1.

    Minecraft clears main depth before these readbacks. Main depth is deliberately
    excluded from this verification; no fabricated geometry or screenshot reading.
    """
    height, width = snapshot['height'], snapshot['width']
    rot = snapshot['f'][33:42].reshape(3, 3, order='F').astype(float)
    inv = snapshot['f'][17:33].reshape(4, 4, order='F').astype(float)
    yy, xx = np.mgrid[:height, :width]
    clip = np.stack(((xx + .5) / width * 2 - 1, (yy + .5) / height * 2 - 1,
                     np.full((height, width), .001), np.ones((height, width))), axis=-1)
    eye4 = clip @ inv.T
    ray = eye4[..., :3] / np.where(np.abs(eye4[..., 3:4]) > 1e-9, eye4[..., 3:4], 1)
    down = rot[:, 1]
    plane_point = first_record['eye'] - (first_lamp['y'] - 1) * down
    plane = float(np.dot(plane_point, down))
    ray_plane = ray @ down
    eye = (ray * (plane / np.where(np.abs(ray_plane) > 1e-9, ray_plane, 1))[..., None]).astype(np.float32)
    return eye, ray_plane < 0, down


def model_nbt(audit: Audit, lamps: list[dict]):
    result = audit.commands('\n'.join(
        f'data get entity @e[tag={LAMP_TAG}.{lamp["slot"]},limit=1] item.components."minecraft:item_model"'
        for lamp in lamps))
    for lamp, row in zip(lamps, result['commands']):
        expected = f'chroma:{SHAPES[lamp["shape"]]}'
        text = '\n'.join(map(str, row.get('messages', [])))
        assert ('"' + expected + '"') in text or ("'" + expected + "'") in text, (lamp['slot'], expected, text)


def camera_command(camera: dict):
    return f'tp @a {camera["x"]:.8f} {camera["y"]:.8f} {camera["z"]:.8f} {camera["yaw"]:.8f} {camera["pitch"]:.8f}'


def run(audit: Audit, original: list[dict]):
    initial = audit.live_status()
    benchmark = audit.forbid_active_benchmark()
    assert initial['pid'] == benchmark['pid'], 'Main bridge and benchmark point to different clients'
    camera = deepcopy(initial['player'])
    report = {'passed': False, 'minecraft': '26.3', 'backend': 'OpenGL', 'resolution': [1920, 1080],
              'pid': initial['pid'], 'initial_state': initial,
              'method': 'Actual vanilla commands and GPU cache/image readback through the isolated test API; no ComputerUse, no synthetic lighting, no runtime shader modifications.',
              'source_identity': 'RGB matching across compact-order changes; equal-color coincidence case is checked as a multiset with 32 distinct automatic addresses.',
              'floor_ROI': 'Known floor top y=1 intersected using actual decoded inverse projection; cleared main depth is not used.',
              'per_source': [], 'shape_rounds': [], 'coincidence': [], 'camera_address_stress': []}
    mixed = deepcopy(original)
    try:
        audit.clear(dummies=True)
        audit.replace(mixed)
        model_nbt(audit, mixed)
        base = audit.snap('mixed-before', pixels=True, keep_image=True)
        matched, check = verify_sources(base, mixed)
        report['mixed_before'] = check
        control = audit.snap('mixed-control', pixels=True)
        control_matched, _ = verify_sources(control, mixed)
        unchanged_camera(base, control)
        unchanged_sources(matched, control_matched)
        eye, ray_below, down = floor_geometry(base, mixed[0], matched[mixed[0]['slot']])
        masks = {}
        for lamp in mixed:
            center = matched[lamp['slot']]['eye'] - (lamp['y'] - 1) * down
            masks[lamp['slot']] = (np.sum((eye - center) ** 2, axis=-1) < 2.45 ** 2) & ray_below
        floor_mask = np.logical_or.reduce(list(masks.values())) & scene_mask(base) & scene_mask(control)
        noise = int(np.max(np.abs(base['rgb'][floor_mask] - control['rgb'][floor_mask])))
        report['control_noise_peak_255'] = noise
        for lamp in mixed:
            removed = False
            try:
                on = audit.snap(f'on-{lamp["slot"]:02}', pixels=True)
                on_records, _ = verify_sources(on, mixed)
                unchanged_camera(base, on)
                audit.commands(f'kill @e[tag={LAMP_TAG}.{lamp["slot"]}]')
                removed = True
                time.sleep(.3)
                off = audit.snap(f'without-{lamp["slot"]:02}', pixels=True, keep_image=True)
                others = [other for other in mixed if other['slot'] != lamp['slot']]
                off_records, off_check = verify_sources(off, others)
                unchanged_camera(on, off)
                unchanged_sources(on_records, off_records)
                mask = masks[lamp['slot']] & scene_mask(on) & scene_mask(off)
                assert mask.sum() >= 20, (lamp['slot'], 'floor ROI outside image')
                delta = on['rgb'][mask] - off['rgb'][mask]
                peak = int(delta.max())
                changed = int(np.count_nonzero(delta.max(axis=1) > max(3, noise)))
                assert peak > max(10, noise * 2) and changed >= 10, (lamp['slot'], 'no independent visible contribution', peak, changed, noise)
                row = {'source': lamp['slot'], 'model': SHAPES[lamp['shape']], 'color': f'#{lamp["rgb"]:06X}',
                       'floor_pixels': int(mask.sum()), 'changed_floor_pixels': changed,
                       'peak_channel_delta_255': peak, 'mean_positive_surface_delta': float(np.maximum(delta, 0).mean()),
                       'other_sources': off_check['count'], 'camera_and_other_parameters_unchanged': True,
                       'capture': str(off['folder'].relative_to(ROOT) / 'main-color.png')}
                report['per_source'].append(row)
                print(json.dumps({'phase': 'contribution', **row}), flush=True)
            finally:
                if removed:
                    audit.commands(lamp_command(lamp))
                    time.sleep(.3)
        del base['rgb'], control['rgb'], eye, masks
        for shape, model in enumerate(SHAPES):
            lamps = deepcopy(mixed)
            for lamp in lamps:
                lamp['shape'] = shape
            audit.replace(lamps)
            model_nbt(audit, lamps)
            snap = audit.snap(f'all-{model}', keep_image=True)
            _, shape_check = verify_sources(snap, lamps)
            shape_check['shape'] = shape
            report['shape_rounds'].append(shape_check)
            print(json.dumps({'phase': 'shape_round', **shape_check}), flush=True)
        center = {'x': float(np.mean([lamp['x'] for lamp in mixed])), 'y': mixed[0]['y'], 'z': float(np.mean([lamp['z'] for lamp in mixed]))}
        for identical in (False, True):
            lamps = deepcopy(mixed)
            for lamp in lamps:
                lamp.update(center)
                if identical:
                    lamp['rgb'], lamp['shape'] = mixed[0]['rgb'], 0
            audit.replace(lamps)
            model_nbt(audit, lamps)
            snap = audit.snap('coincident-identical' if identical else 'coincident-colors', keep_image=True)
            _, coincident_check = verify_sources(snap, lamps, duplicate_identical=identical)
            coincident_check['identical_color_shape_position'] = identical
            report['coincidence'].append(coincident_check)
            print(json.dumps({'phase': 'coincidence', **coincident_check}), flush=True)
        all_addresses = []
        for index in range(16):
            audit.clear()
            audit.clear(dummies=True)
            dummy_count = (0, 1, 2, 3, 7, 11, 16, 23, 32, 47, 64, 83, 96, 112, 128, 160)[index]
            if dummy_count:
                audit.commands('\n'.join(
                    f'summon minecraft:item_display {center["x"] + (j % 16 - 8) * .025:.4f} 18 {center["z"] + 8 + (j // 16) * .025:.4f} '
                    '{Tags:["' + DUMMY_TAG + '"],billboard:"fixed",item_display:"none",view_range:4f,width:0f,height:0f,'
                    'item:{id:"minecraft:paper",count:1},transformation:{scale:[0.02f,0.02f,0.02f]}}'
                    for j in range(dummy_count)))
            audit.commands('\n'.join(lamp_command(lamp) for lamp in mixed))
            theta = math.radians(-10 + 20 * index / 15)
            radius = math.hypot(camera['x'] - center['x'], camera['z'] - center['z'])
            angle = math.atan2(camera['x'] - center['x'], camera['z'] - center['z']) + theta
            current_camera = {'x': center['x'] + radius * math.sin(angle), 'y': camera['y'] + .3 * math.sin(index),
                              'z': center['z'] + radius * math.cos(angle), 'yaw': camera['yaw'] - math.degrees(theta), 'pitch': camera['pitch']}
            audit.commands(camera_command(current_camera))
            time.sleep(.6)
            snap = audit.snap(f'camera-{index:02}', keep_image=index in (0, 15))
            _, stress = verify_sources(snap, mixed)
            stress.update({'view': index, 'dummy_displays': dummy_count, 'requested_camera': current_camera})
            all_addresses.append(tuple(stress['addresses']))
            report['camera_address_stress'].append(stress)
            print(json.dumps({'phase': 'camera_address_stress', **stress}), flush=True)
        assert len(set(all_addresses)) >= 2, 'Stress scene did not change automatic addresses; repeat with different ordinary geometry'
        report['distinct_address_sets_observed'] = len(set(all_addresses))
        report['passed'] = True
    except BaseException as error:
        report['failure'] = str(error)
        report['traceback'] = traceback.format_exc()
        raise
    finally:
        try:
            audit.clear(dummies=True)
            audit.replace(mixed)
            audit.commands(camera_command(camera))
            time.sleep(.7)
            restored = audit.snap('mixed-restored', keep_image=True)
            _, report['restored_mixed'] = verify_sources(restored, mixed)
            report['final_state'] = audit.live_status()
            report['restored'] = True
        except BaseException as error:
            report['restored'] = False
            report['restore_failure'] = str(error)
            report['passed'] = False
        audit.save_report(report)
    assert report['restored'], report.get('restore_failure')
    print(f'PASS: independent contributions, five primary shapes, coincidence, and camera/address stress. {audit.output}', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true', help='Explicitly run against the prepared isolated client; otherwise just print the plan')
    parser.add_argument('--api', type=Path, default=ROOT / 'audit/slotless/api')
    parser.add_argument('--benchmark', type=Path, default=ROOT / 'audit/slotless/benchmark')
    parser.add_argument('--fixture', type=Path, default=ROOT / 'audit/live32/fixture.json')
    parser.add_argument('--output', type=Path, default=ROOT / 'audit/slotless/functional-verification.json')
    parser.add_argument('--prefix', default='slotless-' + datetime.now(timezone.utc).strftime('%H%M%S'))
    args = parser.parse_args()
    assert args.prefix and all(c.isalnum() or c in '_-' for c in args.prefix), 'Prefix must be a simple filename'
    fixture = json.loads(args.fixture.read_text(encoding='utf-8'))
    assert len(fixture) == 32 and len({lamp['rgb'] for lamp in fixture}) == 32, 'Expected 32 distinct fixture colors'
    if not args.run:
        print(json.dumps({'ready': True, 'will_mutate_game': False, 'sources': 32, 'primary_models': SHAPES,
                          'checks': ['32 individual surface contributions', '160 primary model/shape instances',
                                     '32 coincident colors', '32 identical coincident duplicates',
                                     '16 camera positions with ordinary geometry and address changes'],
                          'run': 'Add --run only after the supervisor has finished timed measurements.'}, indent=2))
        return
    run(Audit(args.api, args.benchmark, args.output, args.prefix), fixture)


if __name__ == '__main__':
    main()
