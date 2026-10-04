# Current main: deployment-ready Getting Started (2026-10-04)

- Add `awnphen setup` to verify runtime dependencies, prepare the pinned default model, report compute availability, and surface optional scale-probe status.
- Add `scripts/bootstrap.py` plus Windows and macOS/Linux wrappers for one-command local environment setup.
- Make the default bootstrap install CPU-only PyTorch on Windows/Linux to avoid unexpectedly pulling a large CUDA runtime; GPU users can preserve a preconfigured PyTorch build with `--keep-torch`.
- Make `awnphen studio` resolve the default model before startup and open Awn Studio in the browser automatically; `--no-browser`, `--host`, and `--port` are available for headless/custom launches.
- Expand README setup guidance with the actual first-run UI, model cache behavior, custom-model requirements, and CPU/GPU paths.

---

# Current main: crossing-aware reconstruction (2026-10-02)

- Promote the validated crossing guard into the maintained runtime; each page has independent state.
- Preserve awn identity across resolvable crossings using consistent multiscale arm pairing and observed mask skeleton nodes.
- Clip sharp ambiguous mask junctions and growth entering another spikelet; keep partial ownership and actual Hop replay.
- Mark unresolved crossing endpoints and truncated junctions for review in Awn Studio.
- Expose the loaded pipeline version and crossing-guard state through the model API.
- Align root normalization with the maintained 5 mm minimum-path default; the existing 10 mm² minimum spikelet-area rule is unchanged.
- Synchronize readable Studio source and the installed bundle. Existing projects remain readable; rerun images to use the new algorithm.

The canonical model and public Hugging Face resolver are unchanged. Historical benchmark numbers were produced by earlier versions; this update does not re-evaluate them. This source update does not create a new release tag or replace previously published distribution files.

---

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
