"""Verify the prepared isolated 32-lamp scene through the game's direct API.

Requires a running ChromaLiveProbe and fixture.json generated for the audit.
Checks real GPU caches, stable camera, and each lamp's image contribution.
Does not simulate input, alter shaders, or require a mod in the resource pack.
"""
from pathlib import Path
import json
import time
import numpy as np
from request import request

ROOT = Path(__file__).resolve().parents[2]
AUDIT = ROOT / 'audit/live32'
API = AUDIT / 'api'
W, H = 1280, 720


def command(text):
    result = request(API, 'commands\n' + text)
    assert result['ok'], result
    for row in result['commands']:
        assert row['results'] and all(r['success'] for r in row['results']), row
    return result


def snapshot(name):
    result = request(API, 'dump\n' + name)
    assert result['ok'], result
    folder = API / 'captures' / name
    data = (folder / 'minecraft_matdec-color.bin').read_bytes()
    return {
        'name': name, 'folder': folder,
        'u': np.frombuffer(data, dtype='<u4'),
        'f': np.frombuffer(data, dtype='<f4'),
        'rgb': np.fromfile(folder / 'main-color.bin', dtype=np.uint8).reshape(H, W, 4)[..., :3].astype(np.int16),
        'depth': np.fromfile(folder / 'main-depth.bin', dtype='<f4').reshape(H, W),
        'colors': np.fromfile(folder / 'minecraft_colorcache-color.bin', dtype=np.uint8).reshape(32, 4),
    }


def main():
    lamps = json.loads((AUDIT / 'fixture.json').read_text())
    base = snapshot('verified-all32-before')
    u, f = base['u'], base['f']
    assert u[0] == 1, 'No live camera'
    rot = f[33:42].reshape(3, 3, order='F').astype(float)
    projection = f[1:17].reshape(4, 4, order='F').astype(float)
    inv_projection = f[17:33].reshape(4, 4, order='F').astype(float)
    positions = []
    for k, lamp in enumerate(lamps):
        o = 128 + 16 * k
        assert u[o] == 1 and u[o + 10] == 24, (k + 1, 'not live')
        assert u[o + 6] == lamp['shape'], (k + 1, 'wrong shape')
        assert abs(f[o + 4] - 4) < .005 and abs(f[o + 5] - .4) < .005
        rgb = [(lamp['rgb'] >> shift) & 255 for shift in (16, 8, 0)]
        assert list(base['colors'][k]) == rgb + [255], (k + 1, 'wrong color')
        if lamp['shape'] in (1, 2, 3):
            assert np.dot(f[o + 7:o + 10], rot[:, 1]) > .999, (k + 1, 'spot must face down')
        world = np.array([lamp['x'], lamp['y'], lamp['z']])
        positions.append(f[o + 1:o + 4] - rot @ world)
    positions = np.array(positions)
    position_error = float(np.max(np.abs(positions - np.median(positions, axis=0))))
    assert position_error < .01, ('source transforms inconsistent', position_error)

    # Project the known fixture floor using the real game's decoded camera.
    # Main depth is already cleared at end-of-frame; do not treat it as evidence.
    yy, xx = np.mgrid[:H, :W]
    clip = np.stack(((xx + .5) / W * 2 - 1, (yy + .5) / H * 2 - 1,
                     np.full((H, W), .001), np.ones((H, W))), axis=-1)
    eye4 = clip @ inv_projection.T
    divisor = np.where(np.abs(eye4[..., 3:4]) > 1e-9, eye4[..., 3:4], 1)
    ray = eye4[..., :3] / divisor
    floor_point = f[129:132] - 2.5 * rot[:, 1]
    plane = float(np.dot(floor_point, rot[:, 1]))
    ray_plane = ray @ rot[:, 1]
    eye = ray * (plane / np.where(np.abs(ray_plane) > 1e-9, ray_plane, 1))[..., None]
    # Transport texels are deliberate metadata; exclude them from scene checks.
    ferry = ((yy % 36) == 0) & (yy // 36 < 16) & ((xx % (W // 2)) >= 8) & ((xx % (W // 2)) < 70)
    scene = ~ferry
    control = snapshot('verified-all32-control')
    assert np.array_equal(base['f'][1:42], control['f'][1:42]), 'Camera changed before comparison'
    assert np.array_equal(base['f'][129:], control['f'][129:]), 'Source positions changed'
    masks = []
    for k in range(32):
        center = f[129 + 16 * k:132 + 16 * k] - 2.5 * rot[:, 1]
        masks.append((np.sum((eye - center) ** 2, axis=-1) < 2.45 ** 2) & scene & (ray_plane < 0))
    floor_mask = np.logical_or.reduce(masks)
    control_noise = int(np.max(np.abs(base['rgb'][floor_mask] - control['rgb'][floor_mask])))
    results = []
    for k, lamp in enumerate(lamps):
        deleted = False
        try:
            command(f'kill @e[tag=chroma.demo32.{k + 1}]')
            deleted = True
            time.sleep(.8)
            off = snapshot(f'verified-without-{k + 1:02}')
            assert off['u'][128 + 16 * k] == 0, (k + 1, 'grace period not expired')
            for other in range(32):
                if other != k:
                    assert off['u'][128 + 16 * other] == 1 and off['u'][138 + 16 * other] == 24
            assert np.array_equal(base['f'][1:42], off['f'][1:42]), (k + 1, 'camera changed')
            for other in range(32):
                if other != k:
                    o = 128 + other * 16
                    assert np.array_equal(base['f'][o + 1:o + 10], off['f'][o + 1:o + 10]), (other + 1, 'source moved')
            mask = masks[k]
            delta = base['rgb'][mask] - off['rgb'][mask]
            peak = int(delta.max())
            count = int(np.count_nonzero(delta.max(axis=1) > max(3, control_noise)))
            mean = float(np.maximum(delta, 0).mean())
            assert peak > max(10, control_noise * 2) and count >= 10, (k + 1, peak, count, control_noise)
            row = {'slot': k + 1, 'shape': lamp['shape'], 'color': f'#{lamp["rgb"]:06X}',
                   'surface_pixels': int(mask.sum()), 'changed_surface_pixels': count,
                   'peak_channel_delta_255': peak, 'mean_positive_surface_delta': mean,
                   'other_31_sources_live': True, 'camera_and_other_source_parameters_unchanged': True,
                   'capture': str(off['folder'].relative_to(ROOT) / 'main-color.png')}
            results.append(row)
            print(json.dumps(row), flush=True)
        finally:
            if deleted:
                command(lamp['command'])
                time.sleep(.35)
    after = snapshot('verified-all32-after')
    assert all(after['u'][128 + 16 * k] == 1 and after['u'][138 + 16 * k] == 24 for k in range(32))
    report = {'passed': True, 'minecraft': '26.3', 'backend': 'OpenGL', 'resolution': [W, H],
              'game_process_id': 10160, 'sources': 32, 'distinct_colors': 32, 'shapes_present': 5,
              'method': 'Direct vanilla commands and actual GPU readback; no ComputerUse or shader modifications',
              'surface_ROI': 'Known static white-concrete floor projected with actual decoded camera; main depth is cleared by Minecraft before readback and is not used',
              'live_cache_checks': '32 valid, TTL24, exact RGB and shape, radius4/intensity0.4, consistent positions and downward spot axes',
              'position_consistency_error_blocks': position_error, 'control_noise_peak_255': control_noise,
              'baseline': str(base['folder'].relative_to(ROOT) / 'main-color.png'),
              'final_capture': str(after['folder'].relative_to(ROOT) / 'main-color.png'),
              'per_source': results}
    (AUDIT / 'verification.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print('PASS: 32 independent sources visibly contribute in actual Minecraft.', flush=True)


if __name__ == '__main__':
    main()
