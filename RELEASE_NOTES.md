# v0.1.1 audit-hardening release

AwnPhen 0.1.1 packages the maintained wheat awn phenotyping runtime, Awn Studio, the canonical YOLO11N model binding, one bundled demo image, and lightweight release tests.

## Included

- canonical YOLO11N instance-segmentation inference
- automatic scan-grid calibration
- detection reconciliation and physical cleanup
- Unified Growth reconstruction
- representative-awn selection and root normalization
- calibrated awn-length measurement
- Awn Studio review, editing, and CSV export
- automatic canonical model download from Hugging Face
- bundled demo runnable with `awnphen demo`

## Distribution

Canonical model:

- `anpanchanii/awnphen-yolo11n`
- checkpoint SHA-256: `a7a5cf23bf5d35266e4fa6b1dc0244ee802026a381548bcd202f04b3ebf42097`

Repository:

- https://github.com/Ushiochanii/wheat-awn-phenotyping

License:

- GNU AGPL-3.0

## Audit hardening

A post-publication code audit tightened the release without changing frozen scientific thresholds:

- restored the frozen grid-calibration implementation after detecting release-only drift
- made automatic calibration fail closed when calibration QC is inadequate
- replaced the CLI demo with validation page `IMG_9710`, which passes frozen grid QC at 59 px per 5 mm on both axes
- pinned the canonical Hugging Face model revision and SHA-256
- pinned Ultralytics to the validated 8.4.140 runtime
- hardened localhost origin validation
- removed an obsolete internal launcher
- corrected the Awn Studio integration-report URL
- added release hygiene tests and GitHub Actions checks

See `docs/code-audit-2026-10-01.md` for the audit record.

## Validation

The public runtime has been smoke-tested through the full canonical pipeline on CPU. A built wheel is also unpacked outside the source tree and exercised as part of release validation, verifying that Awn Studio and demo assets are included in the distributable package.

Training pipelines, benchmark history, raw datasets, publication working files, archives, and comparison-model checkpoints are intentionally excluded from the public runtime.
