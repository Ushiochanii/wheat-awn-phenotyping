 1 | # Current main: model library (2026-10-04)
 2 | 
 3 | - Publish the Awn Studio Model Zoo on Hugging Face with YOLO11N, YOLO11M, YOLO11X, Mask R-CNN R50-FPN V2, RF-DETR Seg XL, and Mask2Former Swin-L.
 4 | - Add a **Model library** section to Settings → Measurement with on-demand **Download / Ready** states and model size, positioning, quality notes, and comparable benchmark timing where available.
 5 | - Keep YOLO11N as the only model prepared by the standard setup; larger checkpoints remain opt-in.
 6 | - Add maintained public adapters for Mask R-CNN, RF-DETR segmentation, and Mask2Former segmentation.
 7 | - Add optional `mask2former`, `rfdetr`, and `advanced-models` Python extras instead of bloating the default installation.
 8 | - Move user-supplied local checkpoints under **Advanced · Custom local model**.
 9 | - Expand Getting Started with an official-model comparison table and model-zoo workflow.
10 | 
11 | ---
12 | 
13 | # Current main: deployment-ready Getting Started (2026-10-04)
14 | 
15 | - Retire the legacy `awnphen demo` CLI path; the maintained example now lives inside Awn Studio via **Open sample image**.
16 | - Add `awnphen setup` to verify runtime dependencies, prepare the pinned default model, report compute availability, and surface optional scale-probe status.
17 | - Add `scripts/bootstrap.py` plus Windows and macOS/Linux wrappers for one-command local environment setup.
18 | - Make the default bootstrap install CPU-only PyTorch on Windows/Linux to avoid unexpectedly pulling a large CUDA runtime; GPU users can preserve a preconfigured PyTorch build with `--keep-torch`.
19 | - Make `awnphen studio` resolve the default model before startup and open Awn Studio in the browser automatically; `--no-browser`, `--host`, and `--port` are available for headless/custom launches.
20 | - Expand README setup guidance with the actual first-run UI, model cache behavior, custom-model requirements, and CPU/GPU paths.
21 | 
22 | ---
23 | 
24 | # Current main: crossing-aware reconstruction (2026-10-02)
25 | 
26 | - Promote the validated crossing guard into the maintained runtime; each page has independent state.
27 | - Preserve awn identity across resolvable crossings using consistent multiscale arm pairing and observed mask skeleton nodes.
28 | - Clip sharp ambiguous mask junctions and growth entering another spikelet; keep partial ownership and actual Hop replay.
29 | - Mark unresolved crossing endpoints and truncated junctions for review in Awn Studio.
30 | - Expose the loaded pipeline version and crossing-guard state through the model API.
31 | - Align root normalization with the maintained 5 mm minimum-path default; the existing 10 mm² minimum spikelet-area rule is unchanged.
32 | - Synchronize readable Studio source and the installed bundle. Existing projects remain readable; rerun images to use the new algorithm.
33 | 
34 | The canonical model and public Hugging Face resolver are unchanged. Historical benchmark numbers were produced by earlier versions; this update does not re-evaluate them. This source update does not create a new release tag or replace previously published distribution files.
35 | 
36 | ---
37 | 
38 | # v0.2.0 Awn Studio workflow release
39 | 
40 | AwnPhen 0.2.0 updates the public Awn Studio workflow while preserving the canonical YOLO11N scientific runtime and Hugging Face model distribution established in v0.1.1.
41 | 
42 | ## Highlights
43 | 
44 | - refreshed Awn Studio review workflow with Review Suggested prioritization
45 | - floating Confirm / Reopen action beside the selected representative awn
46 | - simplified measurement sidebar and inline spikelet-ID editing
47 | - redraw mode hides the previous representative path while drawing and restores it on cancel
48 | - review seen/unseen state and improved latest-result navigation
49 | - calibration changes after inference now show a non-blocking rerun recommendation
50 | - browser-session restore and Open Project resume the latest measurement result
51 | - bundled sample reuse avoids duplicate sample cards
52 | - Settings can register compatible local Ultralytics YOLO segmentation checkpoints by path
53 | - selecting a model preloads it through the serialized inference worker, reducing the delay before the next Run/Rerun
54 | - forced onboarding has been removed; workflow guidance lives in the README instead
55 | 
56 | ## Model policy
57 | 
58 | The canonical public model remains YOLO11N from:
59 | 
60 | - `anpanchanii/awnphen-yolo11n`
61 | - checkpoint SHA-256: `a7a5cf23bf5d35266e4fa6b1dc0244ee802026a381548bcd202f04b3ebf42097`
62 | 
63 | Custom local model registration in the public package supports the same Ultralytics YOLO segmentation interface. Research comparison checkpoints such as RF-DETR, Mask2Former, Mask R-CNN, and YOLO11M benchmark weights are not distributed in the public runtime.
64 | 
65 | ## Reliability
66 | 
67 | The release candidate was audited across project persistence, review/edit state, calibration changes, model-service failures, malformed project files, and 100+ real-page browser workloads. The maintained Workbench had no remaining P0/P1 release blockers at the end of the audit.
68 | 
69 | Large projects may still show short UI hitches while full-resolution source images are decoded for sidebar thumbnails. This is a performance limitation rather than a measurement-correctness issue.
70 | 
71 | ## Distribution
72 | 
73 | Repository:
74 | 
75 | - https://github.com/Ushiochanii/wheat-awn-phenotyping
76 | 
77 | License:
78 | 
79 | - GNU AGPL-3.0
80 | 