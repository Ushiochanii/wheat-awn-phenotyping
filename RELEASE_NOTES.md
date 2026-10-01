# v0.1.0 release staging

AwnPhen 0.1.0 packages the maintained wheat awn phenotyping runtime, Awn Studio, the canonical YOLO11N model binding, one bundled demo image, and lightweight release tests.

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

## Validation

The public runtime has been smoke-tested through the full canonical pipeline on CPU. A built wheel was also unpacked outside the source tree and successfully ran the bundled demo, verifying that Awn Studio and demo assets are included in the distributable package.

Training pipelines, benchmark history, raw datasets, publication working files, archives, and comparison-model checkpoints are intentionally excluded from the public runtime.
