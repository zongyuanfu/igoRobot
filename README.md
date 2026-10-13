# Planigo project page

Original HTML, CSS and ES-module JavaScript, inspired by the centered typography and
figure-led organization of [Nerfies](https://nerfies.github.io/) and the
[Academic Project Page Template](https://github.com/eliahuhorwitz/Academic-project-page-template).
No template code, frontend framework, bundler, CDN, analytics or online planning service.
English is the initial publication language. The six scene buttons share one 3D viewer.

## Preview

From the repository root:

```sh
UV_CACHE_DIR=/tmp/planigo-uv-cache uv run --no-sync python -m http.server 8765 --directory website
```

Open http://localhost:8765/. HTTP is required for ES modules and JSON loading;
opening `index.html` through `file://` is not supported.
The publishable page files are tracked by Git; raw `source_runs/` remain ignored.
This does not deploy the page.

## Static delivery and dependencies

All URLs are relative to the page/module and work below a repository path. Deliver
`index.html`, `styles.css`, `main.js`, `charts.js`, `viewer.js`, `assets/`, `data/`, `demos/`, and
`vendor/`. Exclude `source_runs/` and `tools/` from the published artifact. The
browser needs no Python or WebSocket server. One active trajectory is fetched at a
time; robot meshes are shared, cached, and loaded when the demos approach the viewport.
Rendering stops when playback is paused; playback suspends offscreen and in hidden tabs.
WebGL failure leaves the preview, scientific results and manifest downloads available.

Three.js **0.180.0** is vendored under its MIT license. It is a 3D rendering library,
not a frontend framework. `vendor/three.module.js`, `three.core.js`, `OrbitControls.js`,
`loaders/GLTFLoader.js`, and `utils/BufferGeometryUtils.js` are unchanged npm files.

### Viser evaluation

The installed **viser 1.0.30** does expose `get_scene_serializer()`. Its official
[embedded visualization documentation](https://viser.studio/main/embedded_visualizations/)
describes static recordings and a standalone playback client. The previous plan's
claim that Viser necessarily requires a live Python/WebSocket server was incorrect.
We inspected the installed API and official workflow; we did not claim a validated
Viser recording integration. This implementation instead uses native controls and
Three.js to keep the complete page free of a frontend framework, integrate the
seven-dimensional control plot, and share one renderer across the six cases.

## Current method and historical results

The method section reflects the 2026-10-08 full-horizon implementation: 32 cost
waypoints, with final evaluation sampled after retiming at
`N = ceil(T / 0.025 s) + 1`, including both endpoints. The current robot model has
61 spheres. The six browser demonstrations were replanned on 2026-10-11 with the current
32-waypoint configuration and 61-sphere model. The displayed benchmark statistics
remain the 2026-10-04 snapshot (61 cost waypoints, 57 spheres), labelled separately
in the results section.

## Data provenance

`data/results.json` records the source SHA256, config, GPU, build, commit and dirty
worktree status. The full statistics are recomputed from the completed, corrected
800-case batch at:

```
benchmarks/results/homepage_comparison_20261004/full/planigo/
```

Success is **681/800**. Median / P90 synchronized host optimization time is
**0.157659 / 0.167951 s**; median / P90 physical trajectory duration is
**2.080276 / 2.325110 s**. Timing is after warmup on an RTX 4060 Laptop,
Release / sm_89. It is neither end-to-end time nor CUDA event timing.
The snapshot is commit `499b8f9` plus the recorded worktree changes, including
the ESDF coverage fix and benchmark timing instrumentation.
The homepage describes the full-horizon planner, not the 8-control MPC mode.

On 2026-10-04 all 800 Planigo cases were rerun and matched the earlier corrected
batch's control-point hashes and success flags exactly. A CUDA-event cross-check
gave **157.671 / 167.976 ms** median / P90 for the optimization scope. Third-party
code and CUDA build outputs were not changed.

The new comparison uses cuRobo `0.8.0.post1.dev42`, checkout `8e734f3`, in separate
TrajOpt and Full processes. Shared-evaluator success counts are **621/800** and
**624/800**; native success counts are **651/800** and **655/800**. Planning-time
median / P90 is **167.1 / 177.9 ms** for Planigo, **98.7 / 131.3 ms** for cuRobo
TrajOpt, and **116.7 / 465.7 ms** for cuRobo Full. These broader planning scopes
include IK and must not be confused with Planigo's optimize-only time.

`data/comparison.json` contains all configurations, timing scopes and source hashes;
`data/comparison-cases.json` contains the 2,400 case summaries. Native model/IK,
seeds and budgets differ. The overall success gap is concentrated in inverted-box
cases and cannot by itself establish an optimizer advantage. See the configuration and timing scopes in `data/comparison.json` for the
historical protocol.

All six demonstrations were replanned using the current full-horizon build,
canonical OBB scenes, strict IK selection, and base seed 42 plus the problem index.
Each passed the current shared evaluator. Their new trajectories, duration-dependent
evaluation grids, controls, metrics and 11-link FK references are exported together.
Demo timing comes from this replan after a warmup call. It is not batch timing.
Each `data/*-manifest.json` records the run and model fingerprint. The selected
cases remain box/57, flipped/52, small bookshelf/88, thin bookshelf/55, cage/90 and
under-table/14. These are curated successes, not a 6/6 benchmark.

### Refresh current demonstrations

Use a new runs directory to preserve earlier exports:

```sh
JAX_PLATFORMS=cpu uv run --no-sync python website/tools/export_current_demos.py \
  --build-dir igo_solver_pkg/build_full_horizon_32 \
  --runs-dir website/source_runs/current_20261011
# Rebuild the browser data from those saved runs without rerunning the planner:
JAX_PLATFORMS=cpu uv run --no-sync python website/tools/export_current_demos.py \
  --runs-dir website/source_runs/current_20261011 --export-only
```

The exporter validates all six runs before replacing demo assets. It updates the
robot, case list, trajectory data and manifests; benchmark tables and statistics
have their own historical provenance. Run the browser helper with `--previews --teaser` afterwards to refresh all thumbnail images and the homepage video.

### Regeneration

The commands below describe regeneration with the matching historical checkout,
configuration, robot model, CUDA build and local source experiment. The current
32-waypoint configuration intentionally fails the exporter's historical-config
guard for this 61-waypoint batch, including without `--rerun`. To preview the
published snapshot, use the tracked assets directly; regeneration is unnecessary.
To publish new results, first produce and validate a matching batch and exports,
then update the page's result tables and provenance together.

Historical regeneration commands:

```sh
JAX_PLATFORMS=cpu uv run --no-sync python website/tools/export_homepage.py \
  --results-dir benchmarks/results/homepage_comparison_20261004/full/planigo --rerun
# To rebuild browser data from existing exports without rerunning CUDA:
JAX_PLATFORMS=cpu uv run --no-sync python website/tools/export_homepage.py \
  --results-dir benchmarks/results/homepage_comparison_20261004/full/planigo
uv run --no-sync python website/tools/publish_comparison.py \
  benchmarks/results/homepage_comparison_20261004/full
```

The exporter creates new timestamped source runs; it does not overwrite benchmark
results. It checks success, control hashes, physical timestamps and saved EE/FK
agreement. Raw CSVs and build artifacts remain outside the publication artifact.
`data/benchmark-cases.json` is a compact 800-case audit table derived from the batch.

Franka GLB files are conversions of the repository's `assets/franka_description`
DAE meshes, retaining vertex colors. Their Apache-2.0 license is included as
`assets/FRANKA-LICENSE.txt`. Kinematics and collision spheres come from `FrankaModel.load()`, using the shared
FK NPZ and canonical robot YAML. The browser interpolates recorded joint positions and recomputes FK;
this is playback interpolation, not new collision validation. Obstacles use the canonical scene world-frame pose (wxyz) and dimensions saved
by the planner. The displayed collision spheres are the 61 current model spheres,
including both fingers. All 11 link transforms, including fixed 0.04 m finger
joints, use the exported FK parameters. The sphere layer shows base radii;
per-link self-collision padding is recorded but is not drawn as enlarged spheres.

The control-point plot overlays all seven joint angles and control polygons
against physical time, using one consistent color per joint. Velocity and
acceleration plots show saved analytic derivatives normalized by each joint’s
limit, with a shaded ±1 constraint band. All plots share the playback cursor. Its control
polygon is plotted at Greville abscissae; it is never presented as a Cartesian
end-effector B-spline control polygon. Method figures are labeled schematics;
step 03 now illustrates full-trajectory discrete evaluation, with retiming
retained as a supporting implementation detail.

## Browser verification

The offline helper uses Playwright 1.56.1 / Chromium. Install it outside the project
environment or point `PLANIGO_PLAYWRIGHT` at an existing installation:

```sh
PLANIGO_PLAYWRIGHT=/tmp/planigo-web-tools/node_modules/playwright \
PLAYWRIGHT_BROWSERS_PATH=/tmp/planigo-web-browsers \
node website/tools/browser_check.mjs
# Render the previews and short teaser from actual recorded trajectories:
PLANIGO_PLAYWRIGHT=/tmp/planigo-web-tools/node_modules/playwright \
PLAYWRIGHT_BROWSERS_PATH=/tmp/planigo-web-browsers \
node website/tools/browser_check.mjs --previews --teaser
```

Checks cover all six scenes, physical-time scrubbing, playback, display layers,
joint selection, keyboard camera movement, view reset, FK parity, and mobile
overflow. Screenshots are written to `/tmp/planigo-home-{desktop,mobile}.png`.
Set `PLANIGO_URL` to test a repository subpath. Generated preview images and the
teaser are direct renderings, not AI-generated or hand-authored trajectories.

Verified on 2026-10-04 at both `/` and `/website/`: all six cases, rapid switching,
320/390/768/1440px widths, reduced-motion preference, WebGL fallback and no-JavaScript
results. No page errors or failed asset requests in the final run. Maximum browser
FK matrix-element error against the offline reference was `3.105e-7` at the start,
middle and end of each case. The 800-case totals and all six manifest/config/timing
and hash comparisons passed. The updated comparison page also passed the same
browser checks; the full Python suite was 145 passed / 3 skipped. All 2,400 result
rows passed completeness, timing and successful-metric audits. Browser assets total
approximately 16 MB uncompressed;
the 3D library and meshes load on demand, and the first-screen video is about 150 KB.

## Current demo generation (2026-10-11)

Regenerated all six WebP previews and `assets/teaser.webm` from the new trajectories.
The browser helper completed with no page errors at 320/390/768/1440px widths.
Maximum FK matrix error was 3.08e-7; maximum collision-sphere coordinate error was
2.46e-7 m against the exported Python references, including the two finger links.
Playback, scene switching and collision-layer checks passed. Visual acceptance is
left to manual review. `PLANIGO_CHROMIUM` optionally selects an existing Chromium
executable when using the browser helper.

## Publication

Deployment is intentionally separate. The root `.gitignore` excludes only
`/website/source_runs/`; the page sources and assets are tracked. Configure
GitHub Pages to publish the website artifact when ready. No deployment workflow
is installed by this change.

The page title is **Planigo — GPU-Accelerated B-spline Motion Planning with IGO**.
The comparison label **cuRobo · Optimization** denotes the IK + particle/MPPI +
L-BFGS mode with graph fallback disabled, distinct from Schulman et al.’s
sequential-convex TrajOpt algorithm. Internal result keys remain `curobo_trajopt`
for compatibility with the recorded experiments.
