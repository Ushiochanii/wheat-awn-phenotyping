# v0.2.0 Awn Studio workflow release

AwnPhen 0.2.0 updates the public Awn Studio workflow while preserving the canonical YOLO11N scientific runtime and Hugging Face model distribution established in v0.1.1.

## Highlights

- refreshed Awn Studio review workflow with Review Suggested prioritization
- floating Confirm / Reopen action beside the selected representative awn
- simplified measurement sidebar and inline spikelet-ID editing
- redraw mode hides the previous representative path while drawing and restores it on cancel
- review seen/unseen state and improved latest-result navigation
- calibration changes after inference now show a non-blocking rerun recommendation
- browser-session restore and Open Project resume the latest measurement result
- bundled sample reuse avoids duplicate sample cards
- Settings can register compatible local Ultralytics YOLO segmentation checkpoints by path
- selecting a model preloads it through the serialized inference worker, reducing the delay before the next Run/Rerun
- forced onboarding has been removed; workflow guidance lives in the README instead

## Model policy

The canonical public model remains YOLO11N from:

- `anpanchanii/awnphen-yolo11n`
- checkpoint SHA-256: `a7a5cf23bf5d35266e4fa6b1dc0244ee802026a381548bcd202f04b3ebf42097`

Custom local model registration in the public package supports the same Ultralytics YOLO segmentation interface. Research comparison checkpoints such as RF-DETR, Mask2Former, Mask R-CNN, and YOLO11M benchmark weights are not distributed in the public runtime.

## Reliability

The release candidate was audited across project persistence, review/edit state, calibration changes, model-service failures, malformed project files, and 100+ real-page browser workloads. The maintained Workbench had no remaining P0/P1 release blockers at the end of the audit.

Large projects may still show short UI hitches while full-resolution source images are decoded for sidebar thumbnails. This is a performance limitation rather than a measurement-correctness issue.

## Distribution

Repository:

- https://github.com/Ushiochanii/wheat-awn-phenotyping

License:

- GNU AGPL-3.0
