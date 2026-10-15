"""Export completed multi-seed MB800 runs to the static website; no GPU calls."""
import argparse
import hashlib
import json
import re
import sys
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from benchmarks.summarize import summarize_batches
from benchmarks.shared.results import quantiles, summarize
from third_party.website.tools.publish_comparison import GROUPS, NAMES

WEB = Path(__file__).resolve().parents[1]
SEEDS = (42, 142, 242)
PLANNERS = ('planigo', 'curobo_trajopt')
KEYS = ('planner', 'case_id', 'group', 'problem_index', 'seed', 'success',
        'native_success', 'curobo_success', 'failure_codes', 'planner_time_s',
        'pipeline_time_s', 'optimize_time_s', 'optimize_cuda_event_time_s',
        'duration_s', 'free_control_points_sha256', 'selected_goal_q',
        'scene_sha256', 'esdf_grid_sha256')


def public(value):
    """Retain reproducibility metadata using repository-relative paths."""
    if isinstance(value, dict):
        return {public(k): public(v) for k, v in value.items() if k != 'build_dir'}
    if isinstance(value, list):
        return [public(v) for v in value]
    if isinstance(value, str):
        return value.replace(str(ROOT) + '/', '')
    return value


def save(name, value):
    (WEB / 'data' / name).write_text(json.dumps(public(value), separators=(',', ':'), allow_nan=False) + '\n')


def timing_row(planner, report, seed=None):
    t, pipeline = report['planner_time_s'], report['pipeline_time_s']
    label = f'{seed} · {NAMES[planner]}' if seed is not None else NAMES[planner]
    return (f'<tr><th scope="row">{label}</th><td>{report["success"]} / 800</td>'
            f'<td>{t["median"]*1000:.1f} / {t["p90"]*1000:.1f} ms</td>'
            f'<td>{pipeline["median"]:.3f} / {pipeline["p90"]:.3f} s</td></tr>')


def build(source, mpc_source=None):
    source = source.resolve()
    paths = [source / f'full_seed{seed}' / planner for seed in SEEDS for planner in PLANNERS]
    validated = summarize_batches(paths)  # Reject incomplete, mixed-policy or mismatched scenes.
    rows, metadata, reports, hashes = {}, {}, {}, {}
    for seed in SEEDS:
        rows[seed], metadata[seed], reports[seed], hashes[seed] = {}, {}, {}, {}
        for planner in PLANNERS:
            folder = source / f'full_seed{seed}' / planner
            raw = (folder / 'cases.jsonl').read_bytes()
            items = [json.loads(line) for line in raw.splitlines()]
            meta = json.loads((folder / 'metadata.json').read_text())
            if len(items) != 800 or meta['base_seed'] != seed or meta['planner'] != planner:
                raise ValueError(f'Expected MB800 {planner} seed{seed}: {folder}')
            if any(r.get('error') for r in items):
                raise ValueError(f'Infrastructure error in {folder}')
            rows[seed][planner] = items
            metadata[seed][planner] = {k:v for k,v in meta.items() if k != 'cases'}
            reports[seed][planner] = summarize(items)
            hashes[seed][planner] = hashlib.sha256(raw).hexdigest()
    primary, pg_meta = reports[42], metadata[42]['planigo']
    for seed in SEEDS:
        for planner in PLANNERS:
            meta, reference = metadata[seed][planner], metadata[42][planner]
            if meta['git_commit'] != reference['git_commit'] or meta['config_sources'] != reference['config_sources'] or meta['build']['binary_sha256'] != reference['build']['binary_sha256']:
                raise ValueError('Repeated seeds must use the same source, configs and binaries')
            if (meta['build']['build_type'], meta['build']['cuda_architecture']) != ('Release', '120') or 'RTX 5060' not in meta['build']['gpu']:
                raise ValueError('Expected RTX 5060 Release/sm_120 measurements')
    if (pg_meta['model_spheres'], pg_meta['planigo_config']['specification']['optimizer_waypoints'],
        pg_meta['ik_policy'], pg_meta['geometry_profile']) != (61, 32, 'strict', 'canonical_obb_v1'):
        raise ValueError('Expected current canonical 61-sphere, 32-waypoint strict-IK batch')
    common = set.intersection(*[{r['case_id'] for r in rows[42][p] if r['success']} for p in PLANNERS])
    paired = {p: {k: quantiles([r.get(k) for r in rows[42][p] if r['case_id'] in common])
                  for k in ('planner_time_s', 'pipeline_time_s', 'duration_s')} for p in PLANNERS}
    comparison = dict(source=str((source / 'full_seed42').relative_to(ROOT)),
        source_sha256=hashes[42], n=800, primary_seed=42, seeds=list(SEEDS), case_runs=4800,
        summaries=primary, metadata=metadata[42], common_success_n=len(common),
        common_success_metrics=paired, repeats={str(s): dict(summaries=reports[s],
            metadata=metadata[s], source_sha256=hashes[s]) for s in SEEDS},
        validation=validated,
        repeat_note='Same 800 tasks repeated; not 2,400 independent tasks per planner. cuRobo success flags are identical across these seeds.',
        demo_note='Six curated demonstrations were generated separately on 2026-10-11; their timing and seeds are not from this batch.')
    compact = {p: [{**{k: r[k] for k in KEYS if k in r}, 'seed': seed}
                   for seed in SEEDS for r in rows[seed][p]] for p in PLANNERS}
    pg = primary['planigo']
    result = dict(n=800, success=pg['success'], primary_seed=42, seeds=list(SEEDS),
        groups=[dict(group=g, n=v['n'], success=v['success'],
            median_ms=quantiles([r.get('optimize_time_s') for r in rows[42]['planigo'] if r['group']==g])['median']*1000)
            for g,v in pg['groups'].items()], optimize_s=pg['optimize_time_s'],
        duration_s=pg['duration_s'], esdf_s=pg['esdf_time_s'],
        source=str(paths[0].relative_to(ROOT)), source_sha256=hashes[42]['planigo'],
        metadata=pg_meta, repeats={str(s): reports[s]['planigo'] for s in SEEDS})

    mpc = None
    if mpc_source is not None:
        mpc_source = mpc_source.resolve()
        mpc_meta = json.loads((mpc_source / 'metadata.json').read_text())
        mpc_rows = [json.loads(s) for s in (mpc_source / 'cases.jsonl').read_text().splitlines()]
        mpc_report = json.loads((mpc_source / 'report.json').read_text())
        if not mpc_meta['complete'] or len(mpc_rows)!=80 or len({r['case_id'] for r in mpc_rows})!=80:
            raise ValueError('MPC sample must contain 80 unique completed cases')
        if mpc_report['success'] != sum(r['success'] for r in mpc_rows):
            raise ValueError('MPC report does not match case outcomes')
        if any(r['model_sha256'] != pg_meta['model_sha256'] for r in mpc_rows):
            raise ValueError('MPC robot model differs from the current batch')
        cycles = [v for r in mpc_rows for v in r.get('control_cycle_with_fk_s', [])[1:]]
        if (len(cycles), sum(v>.05 for v in cycles)) != (mpc_report['subsequent_cycle_with_fk_s']['n'], mpc_report['subsequent_cycles_with_fk_over_50ms']):
            raise ValueError('MPC cycle timing counts differ from saved rows')
        mpc = dict(source=str(mpc_source.relative_to(ROOT)),
            source_sha256=hashlib.sha256((mpc_source/'cases.jsonl').read_bytes()).hexdigest(),
            summary=mpc_report, metadata={k:v for k,v in mpc_meta.items() if k!='cases'}, execution_sample_dt_s=.05,
            scope='80 stratified tasks, 10 per scene group, seed42. Discrete executed states at 0.05s; not the full-horizon 0.025s acceptance grid.',
            cases=[{k:r[k] for k in ('case_id','group','problem_index','success','failure_codes',
                'mpc_steps','first_optimize_s','median_optimize_s','mean_mpc_step_total_s') if k in r} for r in mpc_rows])

    primary_rows = ''.join(timing_row(p, primary[p]) for p in PLANNERS)
    repeat_rows = ''.join(timing_row(p, reports[s][p], s) for s in SEEDS for p in PLANNERS)
    group_rows = ''.join('<tr><th scope="row">'+title+'</th>'+''.join(
        f'<td><span class="comparison-rate {p}" style="--value:{primary[p]["groups"][g]["success"]}%"><span>{primary[p]["groups"][g]["success"]}%</span></span></td>'
        for p in PLANNERS)+'</tr>' for g,title in GROUPS.items())
    paired_rows = ''.join(f'<tr><th scope="row">{NAMES[p]}</th><td>{paired[p]["planner_time_s"]["median"]*1000:.1f} ms</td><td>{paired[p]["pipeline_time_s"]["median"]:.3f} s</td><td>{paired[p]["duration_s"]["median"]:.3f} s</td></tr>' for p in PLANNERS)
    mpc_html = ''
    if mpc:
        r, c = mpc['summary'], mpc['summary']['subsequent_cycle_with_fk_s']
        mpc_html = f'''<details class="experiment-details"><summary>MPC sample <span>{r['success']} / 80 successful tasks · seed42</span></summary>
        <p class="figure-note">Ten stratified tasks per scene group, with the default 300-iteration initial solve and 150-iteration subsequent solves. Success uses recorded 0.05 s execution states; it is a separate sampling protocol from the full-horizon table.</p>
        <p>Subsequent cycles including warm start, optimization, diagnostics, prefix execution, Python FK and goal checks: median {c['median']*1000:.1f} ms, P90 {c['p90']*1000:.1f} ms, P99 {c['p99']*1000:.1f} ms. {r['subsequent_cycles_with_fk_over_50ms']:,} / {c['n']:,} cycles exceeded the 50 ms execution interval. This configuration did not maintain 20 Hz in the measured sample. Initial IK, map preparation, consumer logging and final evaluation are outside this cycle scope.</p>
        <a href="data/mpc.json" download class="text-link">Download MPC sample results ↓</a></details>'''
    cuda = pg['optimize_cuda_event_time_s']
    cr_meta = metadata[42]['curobo_trajopt']
    cfg = pg_meta['planigo_config']
    section = f'''<section id="results" class="wrap section results" aria-labelledby="results-title">
      <p class="eyebrow">Current experiments · 13–14 October 2026 · RTX 5060</p><h2 id="results-title">Planigo and cuRobo on 800 planning problems</h2>
      <p class="section-intro">The same Robometrics MB start/pose-goal tasks, evaluated with a shared 61-sphere Franka model, canonical OBB scenes and success policy.</p>
      <p class="figure-note">Main tables show seed42. Seeds 42, 142 and 242 repeat the same 800 tasks with fixed settings. The six interactive demonstrations were generated separately on 11 October; their timings and seeds have their own manifests.</p>
      <div class="stat-row">
        <div><strong>{100*pg['success']/800:.3f}<span>%</span></strong><span>Planigo · {pg['success']} / 800 successful plans · seed42</span></div>
        <div><strong>{pg['optimize_time_s']['median']*1000:.1f}<span> ms</span></strong><span>Planigo optimization median · P90 {pg['optimize_time_s']['p90']*1000:.1f} ms</span></div>
        <div><strong>{pg['duration_s']['median']:.3f}<span> s</span></strong><span>Planigo trajectory median · P90 {pg['duration_s']['p90']:.3f} s</span></div>
      </div>
      <figure class="comparison-overview"><h3>Success and runtime · seed42</h3><div class="table-scroll"><table class="comparison-table"><thead><tr><th scope="col">Planner</th><th scope="col">Shared evaluation</th><th scope="col">Planning · median / P90</th><th scope="col">Pipeline · median / P90</th></tr></thead><tbody>{primary_rows}</tbody></table></div>
      <figcaption>All 800 attempts, including failures. Synchronized host planning includes IK and trajectory production, excluding scene setup and shared evaluation. Pipeline adds per-task scene preparation and evaluation; initialization, warmup and artifact writes are excluded. cuRobo Full was not measured in this run.</figcaption></figure>
      <div class="results-grid comparison-grid">
        <figure class="bar-figure"><div class="chart-heading"><h3>Success by scene group · seed42</h3><span>100 problems per group</span></div>
          <table class="results-table comparison-groups"><thead><tr><th scope="col">Scene</th><th scope="col">Planigo</th><th scope="col">Optimization</th></tr></thead><tbody>{group_rows}</tbody></table>
          <figcaption>Shared evaluation includes every failure. The interactive demonstrations are curated successes, not a six-task benchmark.</figcaption></figure>
        <aside class="result-discussion"><h3>What is being compared</h3><p>Planigo performs one MGIGO solve followed by analytic retiming. cuRobo Optimization makes one IK + trajectory-optimization attempt using particle optimization and L-BFGS, with graph fallback disabled.</p>
        <p>Both use canonical robot and scene inputs. Native IK, checker approximations, parameterization, seeding and budgets still differ; this compares configured planning pipelines, not equal-budget optimizers.</p>
        <h3>Reading the results</h3><p>Planigo passes 92/100 inverted-box tasks; cuRobo Optimization passes 27/100. The under-table group remains difficult: Planigo 8/100, cuRobo 26/100. Planigo’s CPU ESDF construction median is {pg['esdf_time_s']['median']:.3f} s, accounting for most of its pipeline time.</p>
        <h3>Native and shared success</h3><p>cuRobo reports {primary['curobo_trajopt']['native_success']}/800 native successes; {primary['curobo_trajopt']['success']}/800 pass the shared acceptance policy. Optimization denotes cuRobo’s particle/L-BFGS mode, distinct from Schulman et al.’s TrajOpt algorithm.</p>
        <a href="data/comparison-cases.json" download class="text-link">Download all 4,800 case summaries ↓</a></aside>
      </div>
      <details class="experiment-details"><summary>Three seed runs <span>Planigo: 667 / 666 / 665 · cuRobo: 615 / 615 / 615</span></summary>
        <p class="figure-note">Seeds 42, 142 and 242. These repeat the same 800 problems; they are not independent new tasks. Percentiles describe task latencies within each run. cuRobo’s success flags are identical across seeds, with mostly identical candidate trajectories.</p>
        <div class="table-scroll"><table class="comparison-table"><thead><tr><th>Seed · planner</th><th>Shared evaluation</th><th>Planning · median / P90</th><th>Pipeline · median / P90</th></tr></thead><tbody>{repeat_rows}</tbody></table></div></details>
      <details class="experiment-details"><summary>Matched successful tasks · seed42 <span>{len(common)} tasks passed by both planners</span></summary>
        <p class="figure-note">Medians on the same {len(common)} tasks. This subset excludes difficult failed tasks; use the full table for aggregate performance.</p>
        <div class="table-scroll"><table class="comparison-table"><thead><tr><th>Planner</th><th>Planning</th><th>Pipeline</th><th>Motion duration</th></tr></thead><tbody>{paired_rows}</tbody></table></div></details>
      {mpc_html}
      <details class="experiment-details"><summary>Experimental setup &amp; success criteria <span>Reproducibility notes</span></summary>
        <div class="setup-grid"><dl><dt>Hardware &amp; schedule</dt><dd>RTX 5060 8GB · Ryzen 7 7700 · Release · sm_120 · CUDA 13.2. Isolated planner processes run sequentially, with one warmup task per scene group. Desktop graphics remained active. The planner order changes across seeds.</dd>
        <dt>Planigo</dt><dd>{cfg['solver']['igo_iterations']} iterations; B=300, B0=100, T0=151; step 0.35; std 0.25 rad. Twelve cubic controls, six free controls, 32 cost waypoints. Solve at 2.5 s, analytically retime with 1.05 margin within [1,5] s. Strict fixed-goal IK; explicit session pool reuses allocations and resets task state. Both planners reset the batch seed before every task.</dd>
        <dt>cuRobo</dt><dd>Version {escape(cr_meta['curobo_version'])}, checkout {cr_meta['curobo_commit'][:7]}. 32 IK seeds, four trajectory-optimization seeds, native B-spline model, CUDA graphs enabled. One attempt, graph fallback disabled. Native goal tolerances are aligned to the common position and quaternion thresholds.</dd>
        <dt>Python &amp; CPU evaluation</dt><dd>NumPy 1.26.4, JAX 0.6.2, Torch 2.13.0+cu132, pybind11 3.0.4. JAX evaluation runs on CPU; OMP, OpenBLAS and MKL use one thread.</dd></dl>
        <dl><dt>Shared evaluation</dt><dd>Canonical 61-sphere Franka model, 694 self-collision pairs; canonical OBB scene geometry; 0.02 m ESDF voxels. Position error ≤ 0.01 m; quaternion error 1 − |q·q*| ≤ 0.001. Environment clearance ≥ 0.01 m, self clearance ≥ 0; OOB, joint, velocity, acceleration and jerk checks. Acceleration ≤ 15 rad/s²; jerk ≤ 500 rad/s³.</dd>
        <dt>Sampling &amp; timing limits</dt><dd>Endpoint-inclusive uniform physical grids with maximum 0.025 s interval. IGO uses analytic B-spline derivatives; cuRobo uses quintic Hermite reconstruction of native q/dq/ddq. Pipeline time may include JITs for unseen evaluation shapes. The headline reports optimization only; compare planners using the broader planning column. Discrete checks do not establish continuous safety.</dd>
        <dt>CUDA event cross-check · seed42</dt><dd>Planigo optimization median / P90: {cuda['median']*1000:.1f} / {cuda['p90']*1000:.1f} ms. Scoped GPU timeline measurements, not kernel-duration sums.</dd>
        <dt>Source &amp; audit</dt><dd>Commit {pg_meta['git_commit'][:7]}; clean benchmark worktree. Six complete MB800 batches passed shared contract and scene-fingerprint checks. <a href="data/comparison.json">Configurations, provenance and per-seed statistics</a> · <a href="data/benchmark-cases.json">800 Planigo seed42 summaries</a>. Previous RTX 4060 Laptop results used different configs and evaluation, so these are not a pure hardware speedup comparison.</dd></dl></div>
      </details>
    </section>'''
    html, count = re.subn(r'<section id="results".*?</section>', lambda _: section, (WEB/'index.html').read_text(), flags=re.S)
    if count != 1:
        raise ValueError('Expected exactly one results section')
    html = html.replace('The comparison uses one dataset, fixed configurations and one measured pass per mode. Different internal robot and collision models limit conclusions about optimizer quality alone.',
        'The comparison uses one dataset, fixed configurations and three repeated seeds. Native IK, checker approximations and budgets limit conclusions about optimizer quality alone.')
    # Write only after all source batches and the HTML replacement have validated.
    save('comparison.json', comparison)
    save('comparison-cases.json', compact)
    save('results.json', result)
    save('benchmark-cases.json', [{**{k:r[k] for k in KEYS if k in r}, 'seed':42} for r in rows[42]['planigo']])
    if mpc:
        save('mpc.json', mpc)
    (WEB/'index.html').write_text(html)
    print(json.dumps(dict(seeds=SEEDS, success={str(s):{p:reports[s][p]['success'] for p in PLANNERS} for s in SEEDS}, common_success_n=len(common), mpc_success=mpc['summary']['success'] if mpc else None)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path, help='directory containing full_seed42/142/242')
    parser.add_argument('--mpc-source', type=Path)
    args = parser.parse_args()
    build(args.source, args.mpc_source)
