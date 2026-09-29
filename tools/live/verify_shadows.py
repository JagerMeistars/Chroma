"""Real-client source-shadow audit; never launches or attaches to Minecraft.

--write-scene writes the two max-exclusive boxes used by the static exporter.
--run requires the isolated audit world, both probes, and no active benchmark.
Debug mode reads linear visibility (0 blocked, 255 lit) from --debug-target.
Without debug mode, --baseline supplies same-view main-color comparisons only.
"""
from pathlib import Path
import argparse
from datetime import datetime, timezone
import json
import math
import time
import traceback

import numpy as np
from request import request
from verify_slotless import Audit, camera_command, unchanged_camera

ROOT = Path(__file__).resolve().parents[2]
TAG = 'chroma.shadowtest'
WALL = {'min': [-1, 1, -1], 'max': [1, 4, 1]}
LAMP = [-3.0, 5.0, 0.0]
MOVED = [3.0, 5.0, 0.0]


def look_at(position, target=(3, 1, 0)):
    dx, dy, dz = np.array(target, dtype=float) - (np.array(position) + [0, 1.62, 0])
    return dict(zip(('x', 'y', 'z'), position), yaw=math.degrees(math.atan2(-dx, dz)),
                pitch=math.degrees(math.atan2(-dy, math.hypot(dx, dz))))


VIEWS = [look_at(p) for p in ((8, 7, 10), (6, 4, -8), (10, 8, 3),
                             (10, 8, -3), (4, 9, 9), (4, 9, -9))]
OFFSCREEN = look_at((3, 3, 4), (7, 1, 2))
SCENE = dict(boxes=[{'min': [-12, 0, -12], 'max': [13, 1, 13]}, WALL],
             light=LAMP, radius=14, intensity=.3, moved_light=MOVED,
             views=VIEWS, offscreen_view=OFFSCREEN,
             bounds={'min': [-16, -4, -16], 'max': [16, 12, 16]})


def segment_hits_box(start, end, box=WALL):
    """Independent analytic slab test for the known fixture's solid blocker."""
    start, end = np.asarray(start, dtype=float), np.asarray(end, dtype=float)
    direction = end - start
    lo, hi = np.asarray(box['min']), np.asarray(box['max'])
    parallel = np.abs(direction) < 1e-10
    outside = np.any(parallel & ((start <= lo) | (start >= hi)), axis=-1)
    divisor = np.where(parallel, 1, direction)
    a, b = (lo - start) / divisor, (hi - start) / divisor
    enter = np.max(np.where(parallel, -np.inf, np.minimum(a, b)), axis=-1)
    leave = np.min(np.where(parallel, np.inf, np.maximum(a, b)), axis=-1)
    return (~outside) & (np.minimum(leave, 1 - 1e-5) > np.maximum(enter, 1e-5))


def floor_points():
    x, z = np.meshgrid(np.arange(-10.5, 10.51, .25), np.arange(-10.5, 10.51, .25))
    return np.column_stack((x.ravel(), np.ones(x.size), z.ravel()))


def camera_data(snap, lamp):
    assert snap['u'][0] == 1 and snap['u'][42] == 1, 'Expected exactly one decoded fixture light'
    valid = np.flatnonzero(snap['u'][128::16] == 1)
    assert len(valid) == 1
    base = 128 + 16 * int(valid[0])
    assert abs(float(snap['f'][base + 4]) - 14) < .02
    assert abs(float(snap['f'][base + 5]) - .3) < .004
    assert int(snap['u'][base + 6]) == 0
    assert tuple(snap['colors'][valid[0]]) == (255, 255, 255, 255)
    rot = snap['f'][33:42].reshape(3, 3, order='F').astype(float)
    proj = snap['f'][1:17].reshape(4, 4, order='F').astype(float)
    eye_light = snap['f'][base + 1:base + 4].astype(float)
    camera = np.asarray(lamp) - rot.T @ eye_light
    return rot, proj, eye_light, camera


def samples(snap, lamp, points, image, wall_present=True):
    rot, proj, eye_light, camera = camera_data(snap, lamp)
    eye = (points - lamp) @ rot.T + eye_light
    clip = np.column_stack((eye, np.ones(len(points)))) @ proj.T
    w = np.where(abs(clip[:, 3]) > 1e-9, clip[:, 3], 1)
    uv = clip[:, :2] / w[:, None] * .5 + .5
    height, width = image.shape[:2]
    pixels = np.floor(uv * [width, height]).astype(int)
    good = (clip[:, 3] > 0) & (uv.min(axis=1) > .002) & (uv.max(axis=1) < .998)
    good &= np.linalg.norm(points - lamp, axis=1) < 13.8
    good &= ~((abs(points[:, 0]) < 1.3) & (abs(points[:, 2]) < 1.3))
    if wall_present:
        good &= ~segment_hits_box(camera, points + [0, .015, 0])
    # Exclude packet/header pixels used by the RP's source transport.
    address = int(snap['u'][128 + int(np.flatnonzero(snap['u'][128::16] == 1)[0]) * 16 + 11])
    px, py = 4 * (address % (snap['width'] // 4)), snap['height'] - 4 - 3 * (address // (snap['width'] // 4))
    full = uv * [snap['width'], snap['height']]
    good &= ~((full[:, 0] >= px - 2) & (full[:, 0] < px + 6) & (full[:, 1] >= py - 3) & (full[:, 1] < py + 4))
    pixels[:, 0] = np.clip(pixels[:, 0], 0, width - 1)
    pixels[:, 1] = np.clip(pixels[:, 1], 0, height - 1)
    return image[pixels[:, 1], pixels[:, 0]], good


def regions(points, lamp):
    # An enclosing emitter cube produces conservative full-umbra and full-light
    # regions, independent of the shader's disk samples or traversal algorithm.
    offsets = np.array([(x, y, z) for x in (-.65, .65) for y in (-.65, .65) for z in (-.65, .65)])
    hit = np.array([segment_hits_box(points + [0, .02, 0], np.asarray(lamp) + offset) for offset in offsets])
    return hit.all(axis=0), ~hit.any(axis=0)


def clear(audit, tag=TAG):
    audit.commands(f'execute if entity @e[tag={tag}] run kill @e[tag={tag}]', allow_cleanup_noop=True)


def lamp_command(position=LAMP):
    return ('summon minecraft:item_display ' + ' '.join(map(str, position)) + ' '
            '{Tags:["' + TAG + '"],billboard:"fixed",item_display:"none",view_range:4f,width:0f,height:0f,'
            'item:{id:"minecraft:paper",count:1,components:{"minecraft:item_model":"chroma:marker",'
            '"minecraft:custom_model_data":{colors:[16777215]}}},transformation:{translation:[0f,0f,0f],'
            'left_rotation:[0f,0f,0f,1f],scale:[14f,0.3f,1f],right_rotation:[0f,0f,0f,1f]}}')


def fill(audit, command):
    assert command.startswith('fill ')
    result = request(audit.api, 'commands\n' + command)
    audit.command_log.append(result)
    assert result.get('ok'), result
    row = result['commands'][0]
    success = bool(row.get('results')) and all(r.get('success') for r in row['results'])
    assert success or row.get('messages') == ['No blocks were filled'], row


def wall(audit, present=True):
    fill(audit, 'fill -1 1 -1 0 3 0 minecraft:' + ('stone' if present else 'air'))


def setup(audit):
    for tag in (TAG, 'chroma.audit128', 'chroma.demo32', 'chroma.test128', 'chroma.slotless.audit.dummy'):
        clear(audit, tag)
    audit.commands(camera_command(VIEWS[0]))
    time.sleep(1)
    fill(audit, 'fill -12 1 -12 12 12 12 minecraft:air')
    fill(audit, 'fill -12 0 -12 12 0 12 minecraft:white_concrete')
    wall(audit)
    audit.commands(lamp_command())
    audit.commands(camera_command(VIEWS[0]))


def select_pack(audit, pack):
    result = request(audit.benchmark, 'select-packs\nvanilla\n' + pack)
    assert result.get('ok'), result
    deadline = time.monotonic() + 60
    while True:
        result = request(audit.benchmark, 'status')
        assert result.get('ok'), result
        if result['reload'] != 'running':
            assert result['reload'] == 'complete', result
            break
        assert time.monotonic() < deadline, 'Resource reload did not complete'
        time.sleep(.2)
    result = request(audit.benchmark, 'configure\n1920\n1080')
    assert result.get('ok'), result
    # The reload future completes before the Mojang overlay finishes fading.
    # Waiting for that fade prevents UI tint from contaminating image metrics.
    time.sleep(2.1)


def capture(audit, label, debug_target):
    snap = audit.snap(label, pixels=True, keep_image=True)
    if debug_target == 'main-color.bin':
        snap['visibility'] = snap['rgb'][..., 0].astype(float) / 255
    elif debug_target:
        targets = {t['file']: t for t in snap['manifest']['targets']}
        assert debug_target in targets, ('Missing debug target', debug_target, list(targets))
        target = targets[debug_target]
        assert target['kind'] == 'color'
        data = np.fromfile(snap['folder'] / debug_target, dtype=np.uint8).reshape(target['height'], target['width'], 4)
        snap['visibility'] = data[..., 0].astype(float) / 255
    return snap


def check(report, check_name, passed, **evidence):
    row = dict(check=check_name, passed=bool(passed), **evidence)
    report['checks'].append(row)
    print(json.dumps(row), flush=True)


def penumbra(audit, report, snap, lamp):
    widths = []
    for x in (2., 8.):
        z = np.arange(0, 10.001, .025)
        points = np.column_stack((np.full(len(z), x), np.ones(len(z)), z))
        values, good = samples(snap, lamp, points, snap['visibility'])
        dark = np.flatnonzero(good & (values <= .1))
        start = dark[-1] if len(dark) else None
        lit = np.flatnonzero(good & (values >= .9) & (np.arange(len(z)) > (start if start is not None else -1)))
        end = lit[0] if len(lit) else None
        width = float(z[end] - z[start]) if start is not None and end is not None else None
        mid = good & (values > .1) & (values < .9)
        row = dict(receiver_x=x, width_blocks=width, intermediate_samples=int(mid.sum()),
                   intermediate_levels=len(np.unique(np.round(values[mid] * 255))))
        report['penumbra'].append(row)
        check(report, f'penumbra-at-{x:g}', width is not None and mid.sum() >= 3 and row['intermediate_levels'] >= 2, **row)
        widths.append(width)
    if all(w is not None for w in widths):
        check(report, 'penumbra-grows-with-blocker-distance', widths[1] > widths[0] + .025, near_blocks=widths[0], far_blocks=widths[1])


def run(audit, args):
    initial, benchmark = audit.live_status(), audit.forbid_active_benchmark()
    assert initial['pid'] == benchmark['pid']
    report = dict(passed=False, mode=args.mode, pack=args.pack, baseline=args.baseline,
                  warm_all_views=args.warm_all_views,
                  debug_target=args.debug_target, pid=initial['pid'], checks=[], views=[], penumbra=[],
                  method='Real Minecraft images and world-floor samples projected with actual GPU matrices; no main-depth readback assumption.',
                  limitations=['Dynamic cache only knows observed geometry; cold unseen geometry is not required to shadow.'] if args.mode == 'dynamic' else ['Static geometry stays baked after world edits until export and resource reload.'])
    points = floor_points()
    reference = None
    try:
        setup(audit)
        if args.setup_only:
            report['setup_only'] = True
            report['passed'] = True
            return
        if args.edges_only:
            select_pack(audit, args.pack)
            time.sleep(args.warmup)
            edge_checks(audit, args, report, points)
            report['passed'] = all(c['passed'] for c in report['checks'])
            assert report['passed'], report
            return
        if args.warm_all_views:
            select_pack(audit, args.pack)
            for view in VIEWS:
                audit.commands(camera_command(view))
                time.sleep(args.warmup)
        cases = [('view-' + str(i), view, LAMP) for i, view in enumerate(VIEWS)]
        cases += [('offscreen-blocker', OFFSCREEN, LAMP), ('moved-source', VIEWS[0], MOVED)]
        for label, view, lamp in cases:
            audit.commands(f'tp @e[tag={TAG}] ' + ' '.join(map(str, LAMP)))
            audit.commands(camera_command(view if args.mode == 'static' else VIEWS[0]))
            if not args.warm_all_views:
                select_pack(audit, args.pack)
            time.sleep(args.warmup if args.mode == 'dynamic' else .5)
            audit.commands(f'tp @e[tag={TAG}] ' + ' '.join(map(str, lamp)))
            audit.commands(camera_command(view))
            time.sleep(.6)
            shadow = capture(audit, label, args.debug_target)
            umbra, lit = regions(points, lamp)
            row = dict(name=label, camera=view, light=lamp, capture=str(shadow['folder']))
            if args.debug_target:
                values, good = samples(shadow, lamp, points, shadow['visibility'])
                blocked, clear_region = values[good & umbra], values[good & lit]
                row.update(umbra_samples=len(blocked), lit_samples=len(clear_region),
                           median_umbra=float(np.median(blocked)) if len(blocked) else None,
                           tenth_percentile_lit=float(np.quantile(clear_region, .1)) if len(clear_region) else None)
                check(report, label + '-visibility', len(blocked) >= 10 and len(clear_region) >= 10 and row['median_umbra'] < .35 and row['tenth_percentile_lit'] > .8, **row)
                if reference is None:
                    reference = (values, good, umbra | lit)
                    penumbra(audit, report, shadow, lamp)
                elif lamp == LAMP:
                    before, seen, core = reference
                    common = good & seen & core & (umbra | lit)
                    difference = np.abs(values[common] - before[common])
                    median = float(np.median(difference)) if len(difference) else 1
                    p95 = float(np.quantile(difference, .95)) if len(difference) else 1
                    check(report, label + '-world-stability', len(difference) >= 50 and median < .08 and p95 < .25,
                          common_floor_samples=len(difference), median_visibility_delta=median, p95_visibility_delta=p95)
                else:
                    before, seen, _ = reference
                    old_umbra, old_lit = regions(points, LAMP)
                    changed = good & seen & ((old_umbra & lit) | (old_lit & umbra))
                    difference = np.abs(values[changed] - before[changed])
                    check(report, 'moving-source-moves-shadow', len(difference) >= 10 and float(np.median(difference)) > .4,
                          changed_geometry_samples=len(difference), median_visibility_delta=float(np.median(difference)) if len(difference) else None)
            else:
                select_pack(audit, args.baseline)
                time.sleep(.4)
                baseline = capture(audit, label + '-baseline', None)
                unchanged_camera(shadow, baseline)
                on, good = samples(shadow, lamp, points, shadow['rgb'].mean(axis=2))
                off, seen = samples(baseline, lamp, points, baseline['rgb'].mean(axis=2))
                delta = off - on
                dark, clear_delta = delta[good & seen & umbra], delta[good & seen & lit]
                row.update(baseline_capture=str(baseline['folder']), umbra_samples=len(dark), lit_samples=len(clear_delta),
                           median_shadow_darkening_255=float(np.median(dark)) if len(dark) else None,
                           median_lit_change_255=float(np.median(np.abs(clear_delta))) if len(clear_delta) else None)
                check(report, label + '-same-view-image', len(dark) >= 10 and len(clear_delta) >= 10 and row['median_shadow_darkening_255'] > 3 and row['median_lit_change_255'] < 4, **row)
            report['views'].append(row)
        # Remove only the real blocker. Dynamic memory should update after observing
        # the empty space; a static export is deliberately unchanged until rebaked.
        audit.commands(f'tp @e[tag={TAG}] ' + ' '.join(map(str, LAMP)))
        audit.commands(camera_command(VIEWS[0]))
        select_pack(audit, args.pack)
        time.sleep(args.warmup)
        wall(audit, False)
        time.sleep(args.warmup)
        removed = capture(audit, 'blocker-removed', args.debug_target)
        if args.debug_target:
            values, good = samples(removed, LAMP, points, removed['visibility'], wall_present=False)
            umbra, _ = regions(points, LAMP)
            selected = values[good & umbra]
            median = float(np.median(selected)) if len(selected) else None
            desired = median is not None and (median > .85 if args.mode == 'dynamic' else median < .35)
            check(report, 'observed-removal-clears-cache' if args.mode == 'dynamic' else 'static-volume-requires-rebake',
                  len(selected) >= 10 and desired, samples=len(selected), median_visibility=median,
                  capture=str(removed['folder']))
        report['passed'] = bool(report['checks']) and all(c['passed'] for c in report['checks'])
    except BaseException as error:
        report.update(failure=str(error), traceback=traceback.format_exc())
        raise
    finally:
        try:
            wall(audit)
            audit.commands(f'tp @e[tag={TAG}] ' + ' '.join(map(str, LAMP)))
            audit.commands(camera_command(VIEWS[0]))
            report['fixture_restored'] = True
        except BaseException as error:
            report.update(passed=False, restore_failure=str(error))
        audit.save_report(report)
    assert report['passed'], f'Shadow checks failed; inspect {audit.output}'


def edge_checks(audit, args, report, points):
    assert args.debug_target, 'Edge checks require a visibility debug pack'
    if args.mode == 'static':
        buried = [0.0, 2.0, 0.0]
        audit.commands(f'tp @e[tag={TAG}] ' + ' '.join(map(str, buried)))
        time.sleep(.6)
        snap = capture(audit, 'buried-source', args.debug_target)
        values, good = samples(snap, buried, points, snap['visibility'])
        check(report, 'buried-source-blocked', good.sum() > 100 and np.quantile(values[good], .95) < .1,
              samples=int(good.sum()), p95_visibility=float(np.quantile(values[good], .95)), capture=str(snap['folder']))
    else:
        audit.commands(camera_command(OFFSCREEN))
        time.sleep(.6)
        before = capture(audit, 'before-zero-sources', args.debug_target)
        clear(audit)
        time.sleep(.6)
        empty = capture(audit, 'zero-sources', args.debug_target)
        time.sleep(.6)
        empty_later = capture(audit, 'zero-sources-later', args.debug_target)
        names = ('minecraft_voxel-color.bin', 'minecraft_voxel_meta-color.bin')
        # Server removal arrives after the first capture; compare metadata only
        # once no source remains, otherwise its frame counter may still advance.
        retained = all((empty['folder']/n).read_bytes() == (empty_later['folder']/n).read_bytes() for n in names)
        retained &= (before['folder']/names[0]).read_bytes() == (empty['folder']/names[0]).read_bytes()
        check(report, 'zero-sources-preserve-geometry', empty['u'][42] == 0 and empty_later['u'][42] == 0 and retained, cache_bytes_identical=retained)
        audit.commands(lamp_command())
        time.sleep(.6)
        snap = capture(audit, 'source-restored-offscreen', args.debug_target)
        values, good = samples(snap, LAMP, points, snap['visibility'])
        umbra, _ = regions(points, LAMP)
        selected = values[good & umbra]
        check(report, 'restored-source-uses-retained-blocker', len(selected) > 100 and np.median(selected) < .1,
              samples=len(selected), median_visibility=float(np.median(selected)), capture=str(snap['folder']))


def self_check():
    assert bool(segment_hits_box([5, 1.02, 0], [-3, 5, 0]))
    assert not bool(segment_hits_box([5, 1.02, 5], [-3, 5, 0]))
    assert not bool(segment_hits_box([5, 2, 0], [6, 2, 0]))
    assert bool(segment_hits_box([0, 2, 5], [0, 2, -5]))
    assert not bool(segment_hits_box([2, 2, 5], [2, 2, -5]))
    umbra, lit = regions(np.array([[5, 1, 0], [-5, 1, 0]]), LAMP)
    assert umbra.tolist() == [True, False] and lit.tolist() == [False, True]
    assert len(VIEWS) == 6 and len(SCENE['boxes']) == 2


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--setup-only', action='store_true')
    parser.add_argument('--edges-only', action='store_true', help='Buried source or zero-source cache retention')
    parser.add_argument('--warm-all-views', action='store_true', help='Observe all six views once, then retain that geometry between camera cases')
    parser.add_argument('--mode', choices=('static', 'dynamic'), default='dynamic')
    parser.add_argument('--pack')
    parser.add_argument('--baseline', default='file/Chroma-Auto-128.zip')
    parser.add_argument('--debug-target', help='RGBA8 target filename; R is linear visibility. Use main-color.bin for debug builds.')
    parser.add_argument('--warmup', type=float, default=3)
    parser.add_argument('--api', type=Path, default=ROOT / 'audit/shadows/api')
    parser.add_argument('--benchmark', type=Path, default=ROOT / 'audit/shadows/benchmark')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--prefix', default='shadows-' + datetime.now(timezone.utc).strftime('%H%M%S'))
    parser.add_argument('--write-scene', type=Path)
    args = parser.parse_args()
    self_check()
    if args.write_scene:
        args.write_scene.parent.mkdir(parents=True, exist_ok=True)
        args.write_scene.write_text(json.dumps(SCENE, indent=2) + '\n', encoding='utf-8')
    if args.run:
        if not args.pack and not args.setup_only:
            parser.error('--pack is required with --run')
        if not 0 <= args.warmup <= 30:
            parser.error('--warmup must be 0..30 seconds')
        run(Audit(args.api, args.benchmark, args.output or ROOT / 'audit/shadows' / (args.mode + '-live.json'), args.prefix), args)
    else:
        print(json.dumps(dict(self_check='passed', will_mutate_game=False, scene=SCENE), indent=2))
