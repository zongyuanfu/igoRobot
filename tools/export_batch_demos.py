"""Export the six homepage demos directly from a completed MB800 batch."""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from third_party.website.tools.export_homepage import CASES, WEB, save
from third_party.website.tools.publish_current_benchmark import public


def export(source):
    import jax.numpy as jnp
    from benchmarks.shared.config import DEFAULT_IGO_FULL, load_planigo_config
    from benchmarks.datasets.canonical_scene import scene_hash
    from planigo.robot.franka import FrankaModel, FRANKA_MAX_VELOCITY
    from planigo.robot.kinematics_jax import forward_kinematics, compute_sphere_positions
    from planigo.trajectory.bspline_full_horizon_math import assemble_control_points, evaluate

    source = source.resolve()
    raw = (source / 'cases.jsonl').read_bytes()
    items = [json.loads(line) for line in raw.splitlines()]
    rows = {r['case_id']: r for r in items}
    meta = json.loads((source / 'metadata.json').read_text())
    model = FrankaModel.load()
    if not meta['complete'] or meta['dataset'] != 'mb' or len(items) != 800 or len(rows) != 800:
        raise ValueError('Expected a complete, unique MB800 batch')
    if meta['model_sha256'] != model.fingerprint or meta['geometry_profile'] != 'canonical_obb_v1':
        raise ValueError('Batch model or geometry differs from the website contract')
    config = meta['planigo_config']
    if config != asdict(load_planigo_config(DEFAULT_IGO_FULL)):
        raise ValueError('Batch planner configuration differs from the current configuration')
    website_result = json.loads((WEB / 'data/results.json').read_text())
    source_hash = hashlib.sha256(raw).hexdigest()
    if website_result['source_sha256'] != source_hash:
        raise ValueError('Use the same batch as the current homepage result tables')

    files, cases = {}, []
    for group, index, title in CASES:
        case_id = f'mb_{group}_{index:04d}'
        metrics = rows[case_id]
        if not metrics['success']:
            raise ValueError(f'The selected demo did not pass: {case_id}')
        trajectory_path = source / 'trajectories' / f'{case_id}.npz'
        with np.load(trajectory_path, allow_pickle=False) as archive:
            arrays = {k: archive[k] for k in archive.files}
        scene = json.loads((source / 'scenes' / f'{case_id}.json').read_text())
        if scene_hash(scene['canonical']) != metrics['scene_sha256']:
            raise ValueError(f'Scene fingerprint mismatch: {case_id}')
        free = arrays['free']
        if hashlib.sha256(free.astype(np.float32).tobytes()).hexdigest() != metrics['free_control_points_sha256']:
            raise ValueError(f'Control fingerprint mismatch: {case_id}')
        duration = float(arrays['duration'])
        assert duration == metrics['duration_s']
        assert len(arrays['q']) == metrics['diagnostic_waypoints']
        times = np.linspace(0, duration, len(arrays['q']))
        controls = assemble_control_points(free, arrays['start_q'], np.zeros(7),
            np.zeros(7), arrays['goal_q'], duration=duration)
        for derivative, key in enumerate(('q', 'dq', 'ddq')):
            np.testing.assert_allclose(arrays[key], evaluate(controls, times / duration,
                derivative, duration=duration), atol=2e-6, rtol=2e-6)
        poses, ee = forward_kinematics(jnp.asarray(arrays['q'][None]), model.fk_params)
        spheres = np.asarray(compute_sphere_positions(poses, model.sphere_centers, model.sphere_link_indices))[0]
        frames = [0, len(times) // 2, len(times) - 1]
        name = f'{group}-{index}'
        files[f'demos/{name}.json'] = dict(id=name, title=title,
            times=times.tolist(), joints=arrays['q'].tolist(),
            velocity=arrays['dq'].tolist(), acceleration=arrays['ddq'].tolist(),
            limits=dict(velocity=FRANKA_MAX_VELOCITY.tolist(),
                acceleration=[config['dynamics']['max_acceleration']] * 7),
            poses=np.asarray(poses)[0].round(7).tolist(),
            ee=np.asarray(ee)[0, :, :3].round(7).tolist(), controls=controls.tolist(),
            scene=scene['canonical'], goal=arrays['goal_pose'].tolist(), duration=duration,
            model_fingerprint=model.fingerprint,
            sphere_reference=[dict(frame=i, centers=spheres[i].round(7).tolist()) for i in frames])
        files[f'data/{name}-manifest.json'] = public(dict(
            schema_version=2, planner=metrics['planner'], trajectory_kind='planned_offline',
            created_at=meta['created_at'], git_commit=meta['git_commit'], git_status=meta['git_status'],
            dataset='mb', group=group, problem_index=index, seed=metrics['seed'],
            start_joints=arrays['start_q'].tolist(), selected_goal_q=arrays['goal_q'].tolist(),
            goal_pose_xyzw=arrays['goal_pose'].tolist(), scene=scene['canonical'],
            workspace_center=scene['workspace_center'], workspace_extent=scene['workspace_extent'],
            build=meta['build'], bspline_full_horizon_config=config, metrics=metrics,
            model_fingerprint=model.fingerprint, geometry_profile=meta['geometry_profile'],
            ik_policy=meta['ik_policy'], batch_source=str(source.relative_to(ROOT)),
            batch_source_sha256=source_hash, source_trajectory=str(trajectory_path.relative_to(ROOT)),
            source_trajectory_sha256=hashlib.sha256(trajectory_path.read_bytes()).hexdigest(),
            timing_note='Measured synchronized host optimization in the completed RTX 5060 MB800 batch after warmup; the displayed trajectory is from that same case.'))
        cases.append(dict(id=name, title=title, group=group, index=index,
            duration=duration, optimize_ms=metrics['optimize_time_s'] * 1000,
            success=True, seed=metrics['seed'], control_hash=metrics['free_control_points_sha256'],
            optimizer_waypoints=metrics['optimizer_waypoints'], evaluation_waypoints=len(times),
            model_fingerprint=model.fingerprint, created_at=meta['created_at']))
    files['data/cases.json'] = cases
    for name, value in files.items():
        save(WEB / name, value)
    print(json.dumps([{k:c[k] for k in ('id', 'seed', 'optimize_ms', 'duration')} for c in cases], indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path, help='completed Planigo batch with saved trajectories and scenes')
    export(parser.parse_args().source)
