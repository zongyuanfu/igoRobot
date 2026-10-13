"""Export verified benchmark trajectories and compact browser assets (offline only)."""
from pathlib import Path
import sys
import json
import argparse
import shutil
import hashlib

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
WEB = ROOT / 'website'
SOURCE = ROOT / 'benchmarks/results/cuda/bspline_full_horizon/oob_fix_20261003/full_validation/2026_10_03_23_04_001_mb_igo_tuning'
CASES = [('box_panda',57,'Box'), ('box_panda_flipped',52,'Box · inverted'),
         ('bookshelf_small_panda',88,'Bookshelf · small'), ('bookshelf_thin_panda',55,'Bookshelf · thin'),
         ('cage_panda',90,'Cage'), ('table_under_pick_panda',14,'Under the table')]

def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, separators=(',', ':'), allow_nan=False))

def validate_export_config(config_path, batch_config):
    """Compare resolved settings with the complete configuration saved by a run."""
    from dataclasses import asdict
    from benchmarks.shared.config import load_planigo_config

    if asdict(load_planigo_config(config_path)) != batch_config:
        raise ValueError('Configuration differs from the completed batch')

def export(rerun=False, source=SOURCE):
    from benchmarks.planners.igo_full_horizon import run_case, create_evaluator, DEFAULT_BUILD_DIR
    from benchmarks.shared.cases import BenchmarkCaseRequest
    from planigo.robot.franka import FrankaModel, FRANKA_MAX_VELOCITY
    from planigo.robot.kinematics_jax import forward_kinematics, compute_sphere_positions
    from planigo.trajectory.bspline_full_horizon_math import assemble_control_points
    import jax.numpy as jnp
    import trimesh

    source=source.resolve()
    rows = [json.loads(s) for s in (source/'cases.jsonl').read_text().splitlines()]
    assert len(rows)==800 and len({r['case_id'] for r in rows})==800
    metadata = json.loads((source/'metadata.json').read_text())
    batch_config=metadata.get('planigo_config') or next(iter(metadata['configs'].values()))
    metadata.get('build', {}).pop('build_dir', None)
    cfg = ROOT/'benchmarks/configs/planners/igo_full_horizon.yml'
    validate_export_config(cfg, batch_config)
    raw = WEB/'source_runs'
    raw.mkdir(parents=True, exist_ok=True)
    if rerun:
        evaluator = create_evaluator(cfg)
        for ordinal,(group,index,_) in enumerate(CASES):
            old = next(r for r in rows if r['group']==group and r['problem_index']==index)
            request = BenchmarkCaseRequest(dataset='mb',group=group,problem_index=index,seed=old['seed'],
                config_path=cfg,build_dir=DEFAULT_BUILD_DIR,output_root=raw,save_trajectory=False)
            if ordinal==0:
                run_case(request,evaluator=evaluator,fixed_goal_q=np.array(old['selected_goal_q'],dtype=np.float32))
            from dataclasses import replace
            result=run_case(replace(request,save_trajectory=True),evaluator=evaluator,
                fixed_goal_q=np.array(old['selected_goal_q'],dtype=np.float32))
            assert result['success'], result['failure_reason']
            assert result['free_control_points_sha256']==old['free_control_points_sha256']
            print(group,index,result['optimize_time_s'],result['result_dir'],flush=True)
    model=FrankaModel.load()
    demos=[]
    for group,index,title in CASES:
        old=next(r for r in rows if r['group']==group and r['problem_index']==index)
        dirs=sorted(raw.glob(f'*_mb_{group}_{index:04d}'))
        if not dirs: raise RuntimeError(f'Missing export: {group}/{index}; run with --rerun')
        folder=dirs[-1]
        manifest=yaml.safe_load((folder/'manifest.yaml').read_text())
        metrics=yaml.safe_load((folder/'metrics.yaml').read_text())
        assert manifest['bspline_full_horizon_config'] == batch_config
        manifest.get('build', {}).pop('build_dir', None)
        assert metrics['success'] and metrics['free_control_points_sha256']==old['free_control_points_sha256']
        read=lambda name: np.loadtxt(folder/name,delimiter=',',skiprows=1)
        joints=read('planned_trajectory_joints.csv')
        times=read('planned_trajectory_time.csv')
        free=read('planned_free_control_points.csv')
        assert hashlib.sha256(free.astype(np.float32).tobytes()).hexdigest()==old['free_control_points_sha256']
        controls=assemble_control_points(free,np.array(manifest['start_joints']),np.zeros(7),np.zeros(7),np.array(manifest['selected_goal_q']),duration=metrics['duration_s'])
        poses,ee=forward_kinematics(jnp.asarray(joints[None]),model.fk_params)
        ee=np.asarray(ee)[0]
        assert np.max(np.abs(ee[:,:3]-read('planned_trajectory_ee.csv')[:,:3]))<1e-5
        assert len(times)==len(joints) and abs(times[-1]-metrics['duration_s'])<1e-6 and np.all(np.diff(times)>0)
        spheres=np.asarray(compute_sphere_positions(poses,model.sphere_centers,model.sphere_link_indices))[0]
        name=f'{group}-{index}'
        provenance={**manifest,'metrics':metrics,'source_run':str(folder.relative_to(ROOT)),
            'batch_source':str(source.relative_to(ROOT)), 'batch_control_hash_matches':True,
            'robot_source':'planigo/robot/franka_canonical.yml + franka_fk_params.npz; assets/franka_description',
            'model_fingerprint': model.fingerprint,
            'timing_note':'This re-export, after warmup; synchronized host optimize time, not end-to-end or CUDA event time.'}
        save(WEB/'data'/f'{name}-manifest.json',provenance)
        data={'id':name,'title':title,'times':times.tolist(),'joints':joints.tolist(),
              'poses':np.asarray(poses)[0].round(7).tolist(),'ee':ee[:,:3].round(7).tolist(),
              'controls':np.asarray(controls).tolist(),'scene':manifest['scene'],
              'velocity':read('planned_trajectory_velocities.csv').tolist(),
              'acceleration':read('planned_trajectory_accelerations.csv').tolist(),
              'limits':{'velocity':FRANKA_MAX_VELOCITY.tolist(),
                        'acceleration':[batch_config['dynamics']['max_acceleration']]*7},
              'goal':manifest['goal_pose_xyzw'],'duration':metrics['duration_s'],
              'model_fingerprint':model.fingerprint,
              'sphere_reference':[{'frame':i,'centers':spheres[i].round(7).tolist()}
                  for i in (0,len(times)//2,len(times)-1)]}
        save(WEB/'demos'/f'{name}.json',data)
        demos.append({'id':name,'title':title,'group':group,'index':index,'duration':metrics['duration_s'],
            'optimize_ms':metrics['optimize_time_s']*1000,'success':True,'seed':metrics['seed'],
            'control_hash':metrics['free_control_points_sha256']})
    save(WEB/'data/cases.json',demos)
    groups=[]
    for group in dict.fromkeys(r['group'] for r in rows):
        subset=[r for r in rows if r['group']==group]
        groups.append({'group':group,'n':len(subset),'success':sum(r['success'] for r in subset),
            'median_ms':float(np.median([r['optimize_time_s'] for r in subset])*1000)})
    quant=lambda key:dict(zip(['median','p90'],np.quantile([r[key] for r in rows],[.5,.9]).tolist()))
    save(WEB/'data/results.json',{'n':len(rows),'success':sum(r['success'] for r in rows),'groups':groups,
        'optimize_s':quant('optimize_time_s'),'duration_s':quant('duration_s'),'esdf_s':quant('esdf_time_s'),
        'source':str(source.relative_to(ROOT)),'source_sha256':hashlib.sha256((source/'cases.jsonl').read_bytes()).hexdigest(),
        'metadata':{k:v for k,v in metadata.items() if k!='cases'}})
    # Ship a small audit table, not the raw experimental artifacts.
    save(WEB/'data/benchmark-cases.json',[{k:r[k] for k in ['case_id','group','problem_index','seed','success','failure_codes','optimize_time_s','duration_s','free_control_points_sha256']} for r in rows])
    save(WEB/'data/robot.json',{'fingerprint':model.fingerprint,'self_buffer':model.self_buffer.tolist(),'centers':model.sphere_centers.tolist(),'radii':model.sphere_radii.tolist(),
        'links':model.sphere_link_indices.tolist(),'fk':{k:np.asarray(v).tolist() for k,v in model.fk_params.items()}})
    assets=WEB/'assets'; assets.mkdir(exist_ok=True)
    for link in [f'link{i}' for i in range(8)]+['hand','finger']:
        mesh=trimesh.load(ROOT/f'assets/franka_description/meshes/visual/{link}.dae',force='scene')
        (assets/f'{link}.glb').write_bytes(mesh.export(file_type='glb'))
    shutil.copyfile(ROOT/'assets/franka_description/LICENSE',assets/'FRANKA-LICENSE.txt')
    print('Exported six verified cases, robot meshes and 800-case results.',flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rerun',action='store_true',help='Re-run the six GPU cases into new source directories')
    parser.add_argument('--results-dir',type=Path,default=SOURCE)
    args=parser.parse_args()
    export(args.rerun,args.results_dir)
