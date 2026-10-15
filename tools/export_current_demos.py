"""Refresh the six website demos from the current planner, independently of batch tables."""
from pathlib import Path
import argparse
from dataclasses import asdict, replace
import hashlib
import json
import sys

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from third_party.website.tools.export_homepage import CASES, WEB, save


def robot_data(model):
    return {
        'fingerprint': model.fingerprint,
        'centers': model.sphere_centers.tolist(),
        'radii': model.sphere_radii.tolist(),
        'links': model.sphere_link_indices.tolist(),
        'self_buffer': model.self_buffer.tolist(),
        'fk': {k: np.asarray(v).tolist() for k, v in model.fk_params.items()},
    }


def generate(config, build_dir, output):
    from benchmarks.planners.igo_full_horizon import create_evaluator, run_case
    from benchmarks.shared.cases import BenchmarkCaseRequest
    from planigo.robot.franka import FrankaModel

    output.mkdir(parents=True, exist_ok=True)
    index_path = output / 'demo_runs.json'
    if index_path.exists():
        raise ValueError('Choose a new runs directory; existing runs are preserved')
    evaluator = create_evaluator(config)
    runs = []
    for ordinal, (group, index, title) in enumerate(CASES):
        request = BenchmarkCaseRequest('mb', group, index, config, 42 + index,
                                       output, build_dir=build_dir)
        options = dict(evaluator=evaluator, ik_policy='strict',
                       geometry_profile='canonical_obb_v1')
        if ordinal == 0:
            run_case(replace(request, save_trajectory=False), **options)
        result = run_case(request, **options)
        runs.append({'group': group, 'index': index, 'title': title,
                     'result_dir': result.get('result_dir'),
                     'success': result['success'], 'failure_codes': result['failure_codes']})
        save(index_path, {'model_fingerprint': FrankaModel.load().fingerprint, 'runs': runs})
        print(group, index, result['success'], result['failure_codes'], flush=True)
    return index_path


def export(index_path, config):
    from benchmarks.shared.config import load_planigo_config
    from planigo.robot.franka import FrankaModel, FRANKA_MAX_VELOCITY
    from planigo.robot.kinematics_jax import forward_kinematics, compute_sphere_positions
    from planigo.trajectory.bspline_full_horizon_math import assemble_control_points
    import jax.numpy as jnp

    model = FrankaModel.load()
    run_index = json.loads(index_path.read_text())
    assert run_index['model_fingerprint'] == model.fingerprint
    runs = run_index['runs']
    assert len(runs) == len(CASES) and all(r['success'] for r in runs), runs
    config_data = asdict(load_planigo_config(config))
    files, cases = {}, []
    for run, (group, index, title) in zip(runs, CASES):
        assert (run['group'], run['index']) == (group, index)
        folder = Path(run['result_dir'])
        manifest = yaml.safe_load((folder / 'manifest.yaml').read_text())
        metrics = yaml.safe_load((folder / 'metrics.yaml').read_text())
        assert manifest['bspline_full_horizon_config'] == config_data
        assert metrics['success']
        read = lambda name: np.loadtxt(folder / name, delimiter=',', skiprows=1)
        joints, times = read('planned_trajectory_joints.csv'), read('planned_trajectory_time.csv')
        free = read('planned_free_control_points.csv')
        assert hashlib.sha256(free.astype(np.float32).tobytes()).hexdigest() == metrics['free_control_points_sha256']
        assert len(times) == len(joints) == metrics['diagnostic_waypoints']
        assert times[0] == 0 and np.all(np.diff(times) > 0)
        assert abs(times[-1] - metrics['duration_s']) < 1e-6
        controls = assemble_control_points(free, np.array(manifest['start_joints']),
            np.zeros(7), np.zeros(7), np.array(manifest['selected_goal_q']), duration=metrics['duration_s'])
        poses, ee = forward_kinematics(jnp.asarray(joints[None]), model.fk_params)
        spheres = np.asarray(compute_sphere_positions(poses, model.sphere_centers, model.sphere_link_indices))[0]
        ee = np.asarray(ee)[0]
        np.testing.assert_allclose(ee[:, :3], read('planned_trajectory_ee.csv')[:, :3], atol=1e-5)
        frames = [0, len(times)//2, len(times)-1]
        name = f'{group}-{index}'
        manifest.get('build', {}).pop('build_dir', None)
        files[f'data/{name}-manifest.json'] = {
            **manifest, 'metrics': metrics, 'model_fingerprint': model.fingerprint,
            'geometry_profile': 'canonical_obb_v1', 'ik_policy': 'strict',
            'source_run': str(folder.relative_to(ROOT)),
            'robot_source': 'planigo/robot/franka_canonical.yml + franka_fk_params.npz',
            'timing_note': 'Current demo replan; synchronized host optimization after warmup.',
        }
        files[f'demos/{name}.json'] = dict(
            id=name, title=title, times=times.tolist(), joints=joints.tolist(),
            velocity=read('planned_trajectory_velocities.csv').tolist(),
            acceleration=read('planned_trajectory_accelerations.csv').tolist(),
            limits={'velocity': FRANKA_MAX_VELOCITY.tolist(),
                    'acceleration': [config_data['dynamics']['max_acceleration']]*7},
            poses=np.asarray(poses)[0].round(7).tolist(), ee=ee[:, :3].round(7).tolist(),
            controls=np.asarray(controls).tolist(), scene=manifest['scene'],
            goal=manifest['goal_pose_xyzw'], duration=metrics['duration_s'],
            model_fingerprint=model.fingerprint,
            sphere_reference=[{'frame': i, 'centers': spheres[i].round(7).tolist()} for i in frames])
        cases.append(dict(id=name, title=title, group=group, index=index,
            duration=metrics['duration_s'], optimize_ms=metrics['optimize_time_s']*1000,
            success=True, seed=metrics['seed'], control_hash=metrics['free_control_points_sha256'],
            optimizer_waypoints=metrics['optimizer_waypoints'],
            evaluation_waypoints=metrics['diagnostic_waypoints'],
            model_fingerprint=model.fingerprint, created_at=manifest['created_at']))
    # Validate every case before replacing any browser asset. Batch results are separate.
    files['data/cases.json'] = cases
    files['data/robot.json'] = robot_data(model)
    for name, value in files.items():
        save(WEB / name, value)
    print('Exported six current demos and the 61-sphere/11-link robot model.', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=ROOT/'benchmarks/configs/planners/igo_full_horizon.yml')
    parser.add_argument('--build-dir', type=Path, default=ROOT/'igo_solver_pkg/build_full_horizon_32')
    parser.add_argument('--runs-dir', type=Path, required=True)
    parser.add_argument('--export-only', action='store_true')
    args = parser.parse_args()
    index_path = args.runs_dir.resolve() / 'demo_runs.json'
    if not args.export_only:
        index_path = generate(args.config.resolve(), args.build_dir.resolve(), args.runs_dir.resolve())
    export(index_path, args.config.resolve())
