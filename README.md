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

Benchmark tables use the 13–14 October 2026 RTX 5060 runs: the same 800 problems
repeated with seeds 42, 142 and 242. The six curated demonstrations are separate
11 October RTX 4060 Laptop recordings, not a benchmark success-rate sample.

See `data/results.json` and `data/comparison.json` for benchmark provenance,
`data/*-manifest.json` for demo provenance, and `data/mpc.json` for the separate
80-task MPC sample. Browser playback interpolates recorded joints; it does not
perform collision validation. These research results do not establish safe
real-robot execution.

## Maintenance

This repository is used as Planigo's `third_party/website` Git submodule. Python
exporters require the Planigo environment and local experiment results; run them
from the Planigo root. For example:

```sh
uv run --no-sync python third_party/website/tools/publish_current_benchmark.py --help
uv run --no-sync python third_party/website/tools/export_current_demos.py --help
```

Use a new `--runs-dir` when generating demonstrations to preserve earlier runs.
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
