# Planigo project page

Static website for [Planigo](https://github.com/zongyuanfu/planigo), a CUDA
B-spline motion-planning research project. Includes six interactive Franka Panda
trajectory recordings and benchmark results. Built with HTML, CSS, JavaScript
ES modules and vendored Three.js; no frontend build step is required.

## Local preview

From the Planigo repository root:

```sh
uv run --no-sync python -m http.server 8765 --directory third_party/website
```

For a standalone website checkout, serve its root with any static HTTP server.
Open <http://localhost:8765/>. Loading through `file://` is unsupported.

## Files and hosting

- `index.html`, `styles.css`, `main.js`, `charts.js`, `viewer.js`: page and viewer.
- `assets/`, `vendor/`: meshes, images, video and browser dependencies.
- `data/`, `demos/`: benchmark summaries, provenance and recorded trajectories.
- `tools/`: data exporters and browser checks for maintainers.

Publish the page files and the `assets/`, `vendor/`, `data/` and `demos/`
directories to a static host. Paths are relative and support repository subpaths.
Exclude `tools/` and local `source_runs/` from deployment. The hosted page requires
no Python service or running planner.

## Data

Benchmark tables use the 18 October 2026 RTX 5060 seed42 reruns of MB800 and
MPiNets1800. Planigo uses path-scored IK and C++ CPU evaluation. Rates and timing
distributions use the Planigo-validated IK cohort, with the same retained task
IDs applied to cuRobo. Failed planning on retained tasks remains in the denominator.
`data/ik-exclusions.json` records every excluded task and reason; original case
records are retained with inclusion flags in `data/comparison-cases.json`.

See `data/comparison.json` for MB and `data/mpinets.json` for MPiNets provenance.
The six interactive trajectories retain their 15 October batch recordings;
static preview images and the teaser retain their 11 October recordings.
`data/*-manifest.json` gives their separate provenance. `data/mpc.json` remains
an archived 80-task sample. These are not measurements from the new runs.

Browser playback interpolates recorded joints; it does not perform collision
validation. These research results do not establish safe real-robot execution.

## Maintenance

This repository is used as Planigo's `third_party/website` Git submodule. Python
exporters require the Planigo environment and local experiment results; run them
from the Planigo root. For example:

```sh
uv run --no-sync python third_party/website/tools/publish_current_benchmark.py \
  benchmarks/results/website_refresh_20261018
```

The benchmark exporter validates complete batches, matching scene hashes and
evaluation policies before writing data. It records exclusion reasons and never
filters on final trajectory success. Historical demo exporters require their
matching configurations and batch provenance; do not mix those recordings with
current benchmark timing.
For independently replanned demos, use `export_current_demos.py` with a new
`--runs-dir` to preserve earlier runs.
For browser checks, install Playwright separately or set `PLANIGO_PLAYWRIGHT` to
an existing installation, then run `node third_party/website/tools/browser_check.mjs`
against the local preview server.

Commit and push website changes in this repository, then update the submodule
commit in Planigo. See Planigo's
[website maintenance guide](https://github.com/zongyuanfu/planigo/blob/main/docs/website.md)
for the workflow.

## Third-party assets

Three.js is distributed under the [MIT license](vendor/THREE-LICENSE.txt).
Franka meshes are distributed under [Apache-2.0](assets/FRANKA-LICENSE.txt).
Visual inspiration: [Nerfies](https://nerfies.github.io/) and the
[Academic Project Page Template](https://github.com/eliahuhorwitz/Academic-project-page-template).
