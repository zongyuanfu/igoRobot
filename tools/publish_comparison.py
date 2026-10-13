"""Build static research tables only from three completed 800-case experiments."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from benchmarks.shared.results import summarize, quantiles

PLANNERS = ("planigo", "curobo_trajopt", "curobo_full")

WEB=ROOT/'website'
NAMES={'planigo':'Planigo','curobo_trajopt':'cuRobo · Optimization','curobo_full':'cuRobo · Full'}
GROUPS={'bookshelf_small_panda':'Bookshelf · small','bookshelf_tall_panda':'Bookshelf · tall',
        'bookshelf_thin_panda':'Bookshelf · thin','box_panda':'Box','box_panda_flipped':'Box · inverted',
        'cage_panda':'Cage','table_pick_panda':'Table pick','table_under_pick_panda':'Under the table'}

def build(source):
    source=source.resolve()
    rows={};summaries={};metadata={};hashes={}
    for p in PLANNERS:
        folder=source/p
        rows[p]=[json.loads(line) for line in (folder/'cases.jsonl').read_text().splitlines()]
        metadata[p]=json.loads((folder/'metadata.json').read_text())
        metadata[p].get('build', {}).pop('build_dir', None)
        assert metadata[p]['complete'] and len(rows[p])==800
        assert len({r['case_id'] for r in rows[p]})==800
        assert not any(r.get('error') for r in rows[p])
        hashes[p]=hashlib.sha256((folder/'cases.jsonl').read_bytes()).hexdigest()
        summaries[p]=summarize(rows[p])
    ids=[{r['case_id'] for r in rows[p]} for p in PLANNERS]
    assert ids[0]==ids[1]==ids[2]
    common=set.intersection(*[{r['case_id'] for r in rows[p] if r['success']} for p in PLANNERS])
    paired={p:{key:quantiles([r.get(key) for r in rows[p] if r['case_id'] in common])
               for key in ('planner_time_s','pipeline_time_s','duration_s')} for p in PLANNERS}
    result={'source':str(source.relative_to(ROOT)),'source_sha256':hashes,'n':800,
            'summaries':summaries,'common_success_n':len(common),'common_success_metrics':paired,
            'metadata':{p:{k:v for k,v in m.items() if k!='cases'} for p,m in metadata.items()}}
    (WEB/'data/comparison.json').write_text(json.dumps(result,indent=2,allow_nan=False))
    keys=('planner','case_id','group','problem_index','seed','success','curobo_success','failure_codes',
          'planner_time_s','pipeline_time_s','optimize_time_s','optimize_cuda_event_time_s','duration_s',
          'free_control_points_sha256','selected_goal_q')
    compact={p:[{k:r[k] for k in keys if k in r} for r in items] for p,items in rows.items()}
    (WEB/'data/comparison-cases.json').write_text(json.dumps(compact,separators=(',',':'),allow_nan=False))
    pg=summaries['planigo'];med=pg['optimize_time_s']['median']*1000;p90=pg['optimize_time_s']['p90']*1000
    duration=pg['duration_s'];rate=100*pg['success']/800
    timing_rows=''
    for p in PLANNERS:
        r=summaries[p];t=r['planner_time_s'];pipeline=r['pipeline_time_s']
        timing_rows+=f'<tr><th scope="row">{NAMES[p]}</th><td>{r["success"]} / 800</td><td>{t["median"]*1000:.1f} / {t["p90"]*1000:.1f} ms</td><td>{pipeline["median"]:.3f} / {pipeline["p90"]:.3f} s</td></tr>'
    group_rows=''
    for g,title in GROUPS.items():
        cells=''
        for p in PLANNERS:
            n=summaries[p]['groups'][g]['success']
            cells+=f'<td><span class="comparison-rate {p}" style="--value:{n}%"><span>{n}%</span></span></td>'
        group_rows+=f'<tr><th scope="row">{title}</th>{cells}</tr>'
    native='; '.join(f'{NAMES[p]}: {summaries[p]["native_success"]}/800' for p in PLANNERS[1:])
    paired_rows=''.join(f'<tr><th scope="row">{NAMES[p]}</th><td>{paired[p]["planner_time_s"]["median"]*1000:.1f} ms</td><td>{paired[p]["pipeline_time_s"]["median"]:.3f} s</td><td>{paired[p]["duration_s"]["median"]:.3f} s</td></tr>' for p in PLANNERS)
    section=f'''<section id="results" class="wrap section results" aria-labelledby="results-title">
      <p class="eyebrow">Preliminary experiments · 4 October 2026</p><h2 id="results-title">Planigo and cuRobo on 800 planning problems</h2>
      <p class="section-intro">The same Robometrics MB start/pose-goal tasks, evaluated with a shared Franka model and success policy.</p>
      <div class="stat-row">
        <div><strong>{rate:.3f}<span>%</span></strong><span>Planigo · {pg['success']} / 800 successful plans</span></div>
        <div><strong>{med:.1f}<span> ms</span></strong><span>Planigo optimization median · P90 {p90:.1f} ms</span></div>
        <div><strong>{duration['median']:.3f}<span> s</span></strong><span>Planigo trajectory median · P90 {duration['p90']:.3f} s</span></div>
      </div>
      <figure class="comparison-overview"><h3>Success and runtime</h3><div class="table-scroll"><table class="comparison-table"><thead><tr><th scope="col">Planner</th><th scope="col">Shared evaluation</th><th scope="col">Planning · median / P90</th><th scope="col">Pipeline · median / P90</th></tr></thead><tbody>{timing_rows}</tbody></table></div>
      <figcaption>Timing includes all 800 attempts, including failures. Planning includes IK and trajectory production, excluding scene construction and shared evaluation; lifecycle differences are detailed below. Pipeline includes per-task world setup and evaluation; one-time construction and warmup are excluded. Native failures without a returned plan skip shared trajectory evaluation.</figcaption></figure>
      <div class="results-grid comparison-grid">
        <figure class="bar-figure"><div class="chart-heading"><h3>Success by scene group</h3><span>100 problems per group</span></div>
          <table class="results-table comparison-groups"><thead><tr><th scope="col">Scene</th><th scope="col">Planigo</th><th scope="col">Optimization</th><th scope="col">Full</th></tr></thead><tbody>{group_rows}</tbody></table>
          <figcaption>Final shared evaluation, including every failure. The six interactive demonstrations above are selected Planigo successes.</figcaption>
        </figure>
        <aside class="result-discussion"><h3>What is being compared</h3><p>Planigo performs one MGIGO solve followed by analytic retiming. cuRobo Optimization makes one IK + trajectory-optimization attempt using particle optimization and L-BFGS, with graph fallback disabled; cuRobo Full permits up to five attempts with graph seeding enabled from attempt 1.</p>
        <p>Native IK, collision representations and search budgets differ. Planigo uses an analytic ESDF and a fixed IK endpoint; cuRobo uses its native Franka model and OBB world. This is a comparison of configured planning pipelines, not an equal-budget optimizer ablation.</p>
        <h3>Reading the results</h3><p>The aggregate success gap is concentrated in the inverted-box group: Planigo passes {pg['groups']['box_panda_flipped']['success']}/100, cuRobo Full {summaries['curobo_full']['groups']['box_panda_flipped']['success']}/100. cuRobo Full passes more cage and under-table tasks. Differences in native IK and geometry need to be audited before attributing these gaps to the optimizers.</p>
        <p>Optimization denotes cuRobo’s particle/L-BFGS pipeline with graph fallback disabled; it is distinct from Schulman et al.’s TrajOpt algorithm.</p><h3>Native and shared success</h3><p>cuRobo's native success counts are {native}. The tables use the shared evaluator instead, with identical goal, clearance, joint and dynamics thresholds.</p><a href="data/comparison-cases.json" download class="text-link">Download all 2,400 case summaries ↓</a></aside>
      </div>
      <details class="experiment-details"><summary>Matched successful tasks <span>{len(common)} tasks passed by all three modes</span></summary>
        <p class="figure-note">Medians on the same {len(common)} tasks. This subset supports like-for-like duration inspection but excludes difficult failed tasks; use the full table above for aggregate performance.</p>
        <div class="table-scroll"><table class="comparison-table"><thead><tr><th>Planner</th><th>Planning</th><th>Pipeline</th><th>Motion duration</th></tr></thead><tbody>{paired_rows}</tbody></table></div>
      </details>
      <details class="experiment-details"><summary>Experimental setup &amp; success criteria <span>Reproducibility notes</span></summary>
        <div class="setup-grid"><dl><dt>Hardware &amp; schedule</dt><dd>RTX 4060 Laptop GPU · Release · sm_89. Three isolated processes, run sequentially after warmup. One measured pass per mode; timing percentiles are across tasks, not repeated-run confidence intervals. Desktop graphics remained active.</dd>
        <dt>Planigo</dt><dd>300 iterations; B=300, B0=100, T0=151; step 0.35; std 0.25 rad. Twelve cubic controls, six free controls, 61 cost waypoints. Solve at 2.5 s, then analytically retime with 1.05 margin within [1,5] s. Seed 42 + problem index.</dd>
        <dt>cuRobo</dt><dd>Version {metadata['curobo_full']['curobo_version']}, checkout {metadata['curobo_full']['curobo_commit'][:7]}. 32 IK seeds, 4 trajectory-optimization seeds, native B-spline trajectory model, CUDA graphs enabled. Seed 42 reset per task. Native position / orientation tolerances: 0.01 m / 0.05 rad. Optimization collision activation distance: 0.02 m. This configuration returns 2.0 s motions. No planner was tuned on this comparison.</dd></dl>
        <dl><dt>Shared evaluation</dt><dd>57-sphere Franka model; 0.02 m ESDF voxels; goal position error ≤ 0.01 m; quaternion error 1 − |q·q*| ≤ 0.001 (dimensionless). Environment clearance ≥ 0.01 m, self clearance ≥ 0; OOB, joint, velocity, acceleration and jerk checks. Acceleration limit 15 rad/s²; jerk limit 500 rad/s³.</dd>
        <dt>Sampling &amp; timing limits</dt><dd>Maximum 0.025 s interval. Planigo and cuRobo use distinct time grids, so this is discrete evaluation, not a swept-volume guarantee. Planigo planning includes per-task session creation and ESDF upload; cuRobo reuses a warmed planner and its world update is counted in pipeline time. Pipeline timing includes first JITs for unseen evaluation shapes. The headline is Planigo optimization only; compare planners using the broader planning column.</dd>
        <dt>CUDA event cross-check</dt><dd>Planigo optimization CUDA-event median / P90: {pg['optimize_cuda_event_time_s']['median']*1000:.1f} / {pg['optimize_cuda_event_time_s']['p90']*1000:.1f} ms. These are scoped GPU timeline measurements, not sums of kernel durations. Displayed comparison times are synchronized host elapsed.</dd>
        <dt>Source &amp; audit</dt><dd>Commit {metadata['planigo']['git_commit'][:7]} plus recorded worktree changes. <a href="data/comparison.json">Full configuration, versions, provenance and statistics</a>. <a href="data/benchmark-cases.json">Planigo-only case summaries</a>.</dd></dl></div>
      </details>
    </section>'''
    path=WEB/'index.html';html=path.read_text()
    html,count=re.subn(r'<section id="results".*?</section>',lambda _:section,html,flags=re.S)
    assert count==1
    html=html.replace('The experiment uses one dataset and seed schedule; it does not establish performance against another planner.',
        'The comparison uses one dataset, fixed configurations and one measured pass per mode. Different internal robot and collision models limit conclusions about optimizer quality alone.')
    path.write_text(html)
    print(json.dumps({'source':str(source),'success':{p:summaries[p]['success'] for p in PLANNERS},'common_success_n':len(common)},indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('source',type=Path)
    build(parser.parse_args().source)
