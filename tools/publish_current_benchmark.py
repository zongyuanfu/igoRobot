"""Publish paired MB/MPiNets batches with an explicit validated-IK cohort."""
import argparse
from collections import Counter
import hashlib
from html import escape
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from benchmarks.shared.results import summarize
from benchmarks.summarize import summarize_batches
from third_party.website.tools.publish_comparison import GROUPS, NAMES

WEB = Path(__file__).resolve().parents[1]
PLANNERS = ('planigo', 'curobo_trajopt')
DATASETS = {'mb': ('MotionBenchMaker', 800), 'mpinets': ('Motion Policy Networks', 1800)}
KEYS = ('planner', 'dataset', 'case_id', 'group', 'problem_index', 'seed', 'success',
        'native_success', 'failure_codes', 'ik_status', 'ik_source', 'solve_calls',
        'planner_time_s', 'pipeline_time_s', 'optimize_time_s', 'optimize_cuda_event_time_s',
        'duration_s', 'free_control_points_sha256', 'selected_goal_q', 'scene_sha256',
        'esdf_grid_sha256')
COHORT = ('A task is included only when Planigo finds a feasible IK endpoint under the shared '
          'pose, collision, OOB and joint-limit checks and enters trajectory optimization. '
          'Apply those same case IDs to both planners. This is conditional planning success '
          'on a Planigo-validated IK cohort, not end-to-end success on the full dataset. '
          'Native cuRobo failures on retained tasks remain failures; its internal IK success '
          'is not independently available in these records.')


def public(value):
    if isinstance(value, dict):
        return {k: public(v) for k, v in value.items() if k != 'build_dir'}
    if isinstance(value, list):
        return [public(v) for v in value]
    if isinstance(value, str):
        return value.replace(str(ROOT) + '/', '')
    return value


def eligible(row):
    """Filter solely on pre-optimization eligibility, never trajectory success."""
    status = row.get('ik_status')
    if status not in ('feasible', 'infeasible_candidate', 'no_solution'):
        raise ValueError(f'Unknown IK status for {row.get("case_id")}: {status}')
    calls = row.get('solve_calls')
    if not isinstance(calls, int) or calls < 0:
        raise ValueError('Missing solve count')
    if status == 'feasible' and calls == 0:
        raise ValueError('Feasible IK without optimization requires investigation')
    if status != 'feasible' and (calls or row.get('success')):
        raise ValueError('Strict IK batch contains an optimized invalid endpoint')
    return status == 'feasible' and calls > 0


def load_dataset(source, dataset):
    paths = [source / dataset / p for p in PLANNERS]
    summarize_batches(paths)  # Checks completeness, contracts and paired scene hashes.
    rows, metadata, hashes = {}, {}, {}
    for planner, folder in zip(PLANNERS, paths):
        raw = (folder / 'cases.jsonl').read_bytes()
        rows[planner] = [json.loads(line) for line in raw.splitlines()]
        meta = json.loads((folder / 'metadata.json').read_text())
        if (meta['dataset'] != dataset or meta['base_seed'] != 42 or
                len(rows[planner]) != DATASETS[dataset][1] or not meta['complete']):
            raise ValueError(f'Expected complete seed42 {dataset} batch: {folder}')
        if any(r.get('error') or r.get('failure_kind') == 'infra_error' for r in rows[planner]):
            raise ValueError('Infrastructure failures cannot be published')
        if meta['ik_policy'] != 'strict':
            raise ValueError('Expected strict IK policy')
        metadata[planner] = {k: v for k, v in meta.items() if k != 'cases'}
        hashes[planner] = hashlib.sha256(raw).hexdigest()
    ids = {r['case_id'] for r in rows['planigo'] if eligible(r)}
    if not ids:
        raise ValueError('Empty valid-IK cohort')
    excluded = [dict(case_id=r['case_id'], ik_status=r['ik_status'],
                     reason=r.get('failure_codes', []), ik_source=r.get('ik_source'))
                for r in rows['planigo'] if r['case_id'] not in ids]
    reports = {p: summarize([r for r in rows[p] if r['case_id'] in ids]) for p in PLANNERS}
    compact = {p: [dict({k: r[k] for k in KEYS if k in r},
                       included=r['case_id'] in ids) for r in rows[p]] for p in PLANNERS}
    return dict(dataset=dataset, source=str((source / dataset).relative_to(ROOT)),
                source_sha256=hashes, primary_seed=42, total_n=len(rows['planigo']),
                n=len(ids), excluded_n=len(excluded), cohort_policy=COHORT,
                exclusion_counts=dict(Counter(r['ik_status'] for r in excluded)),
                exclusions=excluded, summaries=reports, metadata=metadata,
                validation=dict(complete=True, paired_scene_hashes_match=True,
                                shared_evaluation_contract=True)), compact


def latency(stats):
    if stats['median'] is None:
        return '—'
    return f'{stats["median"]*1000:.1f} / {stats["p90"]*1000:.1f} ms'


def table(report):
    rows = ''.join(f'<tr><th scope="row">{NAMES[p]}</th>'
        f'<td>{r["success"]} / {r["n"]} ({100*r["success"]/r["n"]:.2f}%)</td>'
        f'<td>{latency(r["planner_time_s"])}</td><td>{latency(r["pipeline_time_s"])}</td></tr>'
        for p, r in report['summaries'].items())
    return ('<div class="table-scroll"><table class="comparison-table"><thead><tr>'
            '<th>Planner</th><th>Success · valid IK</th><th>Planning · median / P90</th>'
            '<th>Pipeline · median / P90</th></tr></thead><tbody>' + rows + '</tbody></table></div>')


def group_table(report):
    groups = report['summaries']['planigo']['groups']
    rows = []
    for group in groups:
        cells = []
        for planner in PLANNERS:
            g = report['summaries'][planner]['groups'][group]
            # summarize stores counts, not percentages.
            cells.append(f'<td>{g["success"]} / {g["n"]} ({100*g["success"]/g["n"]:.1f}%)</td>')
        rows.append(f'<tr><th scope="row">{escape(GROUPS.get(group, group))}</th>{"".join(cells)}</tr>')
    return ('<div class="table-scroll"><table class="results-table"><thead><tr><th>Scene</th>'
            '<th>Planigo</th><th>cuRobo · Optimization</th></tr></thead><tbody>' +
            ''.join(rows) + '</tbody></table></div>')


def build(source):
    source = source.resolve()
    reports, cases = {}, {}
    for dataset in DATASETS:
        reports[dataset], cases[dataset] = load_dataset(source, dataset)
    mb, mp = reports['mb'], reports['mpinets']
    meta = mb['metadata']['planigo']
    cfg = meta['planigo_config']
    policy = meta['config_sources']['evaluation']['resolved']
    for report in reports.values():
        for m in report['metadata'].values():
            if (m['git_commit'] != meta['git_commit'] or m['planigo_config'] != cfg or
                    m['config_sources']['evaluation']['resolved'] != policy):
                raise ValueError('Datasets must use the same code and configurations')
    pg = mb['summaries']['planigo']
    date = meta['created_at'][:10]
    blocks = []
    for dataset, report in reports.items():
        blocks.append(f'''<figure class="comparison-overview"><h3>{DATASETS[dataset][0]} · seed42</h3>
          <p>{report['n']:,} valid-IK tasks from {report['total_n']:,}; {report['excluded_n']:,} excluded before optimization. Both planners use the same retained tasks.</p>
          {table(report)}<figcaption>Success and runtime include unsuccessful planning on retained tasks. IK-invalid tasks are excluded from both denominators and timing distributions.</figcaption></figure>
          <details class="experiment-details"><summary>Success by scene · {DATASETS[dataset][0]}</summary>{group_table(report)}</details>''')
    section = f'''<section id="results" class="wrap section results" aria-labelledby="results-title">
      <p class="eyebrow">Current experiments · {date} · RTX 5060</p>
      <h2 id="results-title">Planning after valid IK</h2>
      <p class="section-intro">Fresh runs on MotionBenchMaker and Motion Policy Networks, with path-scored IK selection and C++ CPU evaluation.</p>
      <p class="figure-note">One seed42 run per planner and dataset. These are conditional success rates on a validated-IK cohort; they are not directly comparable to the previous all-task rates.</p>
      <div class="stat-row">
        <div><strong>{100*pg['success']/pg['n']:.2f}<span>%</span></strong><span>MB · {pg['success']} / {pg['n']} valid-IK tasks</span></div>
        <div><strong>{pg['optimize_time_s']['median']*1000:.1f}<span> ms</span></strong><span>MB optimization median · P90 {pg['optimize_time_s']['p90']*1000:.1f} ms</span></div>
        <div><strong>{100*mp['summaries']['planigo']['success']/mp['n']:.2f}<span>%</span></strong><span>MPiNets · {mp['summaries']['planigo']['success']} / {mp['n']} valid-IK tasks</span></div>
      </div>
      {''.join(blocks)}
      <div class="setup-grid">
        <div><h3>Which tasks are counted?</h3><p>A task needs a Planigo IK endpoint that passes the shared pose, collision, map-boundary and joint-limit checks. The same retained task IDs are used for cuRobo. Reference IK can be replaced by a valid cuRobo fallback endpoint.</p>
        <p>MPiNets excludes {mp['excluded_n']} tasks and MB excludes {mb['excluded_n']}. This filter uses endpoint feasibility before trajectory optimization, never the final outcome. Every failed trajectory on the retained set still counts as a failure.</p>
        <p>The cohort depends on Planigo’s IK procedure. cuRobo uses its own internal IK; its native failures on retained tasks remain in the comparison. No unavailable internal status is inferred.</p>
        <a class="text-link" href="data/ik-exclusions.json">Download excluded task IDs and reasons ↓</a></div>
        <div><h3>What the timings include</h3><p>Planning is synchronized host time including IK, optimization, retiming and trajectory production. Pipeline adds per-task scene preparation and final evaluation. Warmup, initialization and artifact writes are excluded. All medians and P90 values use the retained tasks, including planning failures.</p>
        <p>The headline optimization latency is Planigo’s solver scope only. Use the planning and pipeline columns when comparing methods. The previous 15 October page used 300 iterations and 10 mm clearance; this run uses 120 iterations and 5 mm. Timing and success changes are not attributable to the C++ backend alone.</p>
        <p>Each planner runs in a separate process, sequentially, with one warmup task per scene group. One seed provides no estimate of seed-to-seed variability.</p></div>
      </div>
      <details class="experiment-details"><summary>Configuration and provenance</summary><div class="setup-grid">
        <dl><dt>Planigo</dt><dd>{cfg['solver']['igo_iterations']} iterations; B={cfg['solver']['igo_B']}, B0={cfg['solver']['igo_B0']}, T0={cfg['solver']['igo_T0']}; step {cfg['solver']['igo_dt']}; std {cfg['solver']['control_point_std']} rad. Twelve cubic controls, six free controls, 32 optimization waypoints. One solve with analytic retiming. path_score_v1, 64 reference samples, C++ IK geometry and final evaluation.</dd>
        <dt>Hardware</dt><dd>RTX 5060 · Release/sm_120 · CPU thread counts fixed to one. Full hardware and binary metadata are included in the download.</dd>
        <dt>cuRobo</dt><dd>Optimization mode: one native IK + particle/L-BFGS attempt, graph fallback disabled. Internal seeding and collision checks differ from Planigo.</dd></dl>
        <dl><dt>Shared acceptance</dt><dd>Canonical 61-sphere Franka model and OBB scenes; {policy['voxel_size']} m ESDF voxels; position error ≤ {policy['position_tolerance_m']} m; quaternion error ≤ {policy['orientation_tolerance_quat']}; environment clearance ≥ {policy['environment_clearance_m']} m; self clearance ≥ {policy['self_clearance_m']} m. Acceleration ≤ {policy['max_acceleration']} rad/s²; jerk ≤ {policy['max_jerk']} rad/s³. Endpoint-inclusive samples at ≤ {policy['maximum_dt_s']} s, plus OOB, joint and velocity checks.</dd>
        <dt>Source</dt><dd>Planigo {meta['git_commit'][:7]}; Robometrics 0.3.0. Four completed batches; raw records remain available locally. Recorded worktree state and configuration hashes are included with the data. Discrete checks do not establish continuous collision safety.</dd>
        <dt>Downloads</dt><dd><a href="data/comparison.json">MB statistics and provenance</a> · <a href="data/mpinets.json">MPiNets statistics and provenance</a> · <a href="data/comparison-cases.json">All case records with inclusion flags</a></dd></dl>
      </div></details>
      <p class="figure-note">The six interactive demonstrations and the archived MPC sample retain their separately dated recordings; their timings are not measurements from these new runs. <a href="data/mpc.json">Archived MPC sample</a>.</p>
    </section>'''
    html, count = re.subn(r'<section id="results".*?</section>', lambda _: section, (WEB/'index.html').read_text(), flags=re.S)
    if count != 1:
        raise ValueError('Expected one results section')
    html = html.replace('The current comparison uses one dataset, fixed configurations and seed42.',
                        'The current comparison uses two datasets, a shared valid-IK cohort, fixed configurations and seed42.')
    html = html.replace('the interactive viewer below uses the latest benchmark trajectories',
                        'the interactive viewer below uses separately dated benchmark trajectories')
    html = html.replace('Explore six interactive Franka Panda trajectories and results on 800 Robometrics problems.',
                        'Explore six Franka Panda trajectories and valid-IK benchmark results on MotionBenchMaker and Motion Policy Networks.')
    html = re.sub(r'\d+ iterations · \d+ samples per iteration',
                  f"{cfg['solver']['igo_iterations']} iterations · {cfg['solver']['igo_B']} samples per iteration", html)
    html = re.sub(r'Current full-horizon method, updated [^.]+\.',
                  f'Current full-horizon method, updated {date}.', html)
    html = html.replace('Twelve control points describe a continuous joint-space curve.',
        'Feasible IK endpoints are ranked by a 64-sample reference-path score. Twelve control points describe a continuous joint-space curve.') if 'Feasible IK endpoints are ranked' not in html else html
    html = html.replace('After analytic retiming, evaluate the complete trajectory',
        'After analytic retiming, a C++ CPU evaluator checks the complete trajectory')
    result = dict(n=pg['n'], total_n=mb['total_n'], success=pg['success'], primary_seed=42,
                  seeds=[42], excluded_n=mb['excluded_n'], cohort_policy=COHORT,
                  optimize_s=pg['optimize_time_s'], duration_s=pg['duration_s'],
                  esdf_s=pg['esdf_time_s'], metadata=meta,
                  groups=[dict(group=g, n=v['n'], success=v['success']) for g,v in pg['groups'].items()],
                  source=mb['source']+'/planigo', source_sha256=mb['source_sha256']['planigo'])
    outputs = {'comparison.json': mb, 'mpinets.json': mp, 'results.json': result,
               'comparison-cases.json': cases, 'benchmark-cases.json': cases['mb']['planigo'],
               'ik-exclusions.json': {d: dict(policy=COHORT, total_n=r['total_n'], n=r['n'],
                    excluded_n=r['excluded_n'], cases=r['exclusions']) for d, r in reports.items()}}
    for name, value in outputs.items():
        (WEB/'data'/name).write_text(json.dumps(public(value), separators=(',', ':'), allow_nan=False)+'\n')
    (WEB/'index.html').write_text(html)
    print(json.dumps({d: dict(n=r['n'], excluded=r['excluded_n'], success={p:s['success'] for p,s in r['summaries'].items()}) for d,r in reports.items()}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path, help='directory containing mb/ and mpinets/ paired batches')
    build(parser.parse_args().source)
