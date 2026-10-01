# AwnPhen / Awn Studio

Automated wheat awn phenotyping from scanned spike images, with physical reconstruction and human review.

## Quick Start

Python 3.10+ is required.

```bash
git clone https://github.com/Ushiochanii/wheat-awn-phenotyping.git
cd wheat-awn-phenotyping
python -m venv .venv
pip install -e .
```

Run the bundled example:

```bash
awnphen demo
```

For your own image:

```bash
awnphen predict path/to/image.jpg --output runs/my-image
```

The canonical YOLO11N checkpoint is downloaded automatically from Hugging Face:

`anpanchanii/awnphen-yolo11n`

For offline or pinned-checkpoint use, pass `--weights /path/to/best.pt` or set `AWNPHEN_WEIGHTS`.

Physical lengths require a valid calibration in millimetres per pixel. The CLI estimates it from the scan grid by default; use `--mm-per-px` only when you have an explicit calibration.

To launch the interactive Awn Studio:

```bash
awnphen studio
```

Awn Studio also supports an optional dedicated spikelet-scale probe through `AWNPHEN_SCALE_PROBE_WEIGHTS`; when it is absent, resolution diagnostics safely remain unassessed and the original image is retained.

## What the pipeline does

```text
image
 -> tiled instance segmentation
 -> detection evidence
 -> physical reconstruction (Unified Growth)
 -> representative awn
 -> calibrated measurement
 -> review / edit / export in Awn Studio
```

The canonical inference configuration uses 640 px tiles with stride 320.

## Public scope

This repository is intentionally a runtime release, not a dump of the research workspace. It includes the maintained inference/measurement route, Awn Studio, one reproducible example, and tests. Training history, raw research datasets, benchmark workspaces, publication drafts, archived algorithms, caches, and comparison-model checkpoints are excluded.

## Output

The command-line runtime writes reproducible intermediate artifacts under the selected output directory. Awn Studio provides the user-facing measurement review and CSV export workflow.

## License

AwnPhen is distributed under the GNU Affero General Public License v3.0 (AGPL-3.0). The canonical YOLO11N checkpoint is also released under AGPL-3.0. See `LICENSE` and `THIRD_PARTY_NOTICES.md`.

If you need to use Ultralytics YOLO or the derived checkpoint without the AGPL-3.0 obligations, consult Ultralytics for applicable commercial licensing.

## Release status

The canonical Hugging Face model repository is configured and the end-to-end demo has been smoke-tested with the public runtime. The local release staging is technically ready for repository publication after the remaining metadata and repository-hosting details are filled in.

See `RELEASE_NOTES.md` and `docs/architecture.md`.
