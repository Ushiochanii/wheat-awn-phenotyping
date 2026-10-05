# 2026-10-05 Legacy physical-pipeline treasure audit

## Scope

This audit was triggered by a page-edge spikelet false-positive regression observed in the
current Awn Studio / Unified Growth route. The goals were:

1. restore the previously validated page-border artifact diagnostic at the current
   Unified Growth spikelet-premerge boundary;
2. identify older physical/reconstruction logic that was not carried into the
   current mainline and decide whether it is still worth evaluating.

The locked Test11 set was not used for threshold selection or tuning. Safety checks
below use train + validation human spikelet annotations only.

## Border-artifact migration

The old logic was not deleted. It remains in:

- `src/awnphen/phenotyping/physical/spikelet_cleanup.py`
- historical origin: `src/awnphen_next/border_artifact.py` at commit `238727a`
- implementation label: `phase4c_border_strip_diagnostic_v1`

Its policy is intentionally conservative. A spikelet is rejected as a border strip
only when all three conditions hold:

1. the geometry touches the page border within 2 px;
2. the layout-free local-neighbor evaluator marks it `isolated_small_suspicious`;
3. its bounding-box major axis is parallel to the touched border, with aspect ratio
   at least 2.0.

The Workbench still ran this old physical-spikelet cleanup on its seed objects.
However, the newer Unified Growth page runner independently re-reconciled spikelet
evidence and called `preprocess_spikelet_hypotheses()` without page dimensions or
the old border diagnostic. Therefore a spikelet rejected by the outer Workbench
cleanup could still enter Unified Growth orientation, seeding, and growth context.

The current migration reuses the existing implementation rather than duplicating it:

- `src/awnphen/phenotyping/detection/spikelet_premerge.py`
  now accepts source evidence and optional page dimensions, runs the existing
  layout-free evaluator, calls `evaluate_border_artifact()`, and records
  `border_artifact` as a filter reason;
- `src/awnphen/phenotyping/physical/growth/pipeline.py` supplies source evidence and
  page dimensions to premerge;
- `src/awnphen/pipeline/workbench.py` includes page width/height in the per-page
  calibration/context mapping used by Unified Growth.

The existing premerge rules remain independent:

- `tiny_area`: area < 10 mm²;
- `awn_overlap_contamination`;
- `oversized_area_and_length`: area > 250 mm² AND calibrated major axis > 45 mm;
- fragment attachment.

### Safety check

The legacy border-artifact rule was replayed over all 4,273 human spikelet
annotations in train + validation. It rejected **0 / 4,273** GT spikelets.

Focused regression tests after migration:

- spikelet premerge;
- Unified Growth;
- Workbench pipeline service.

Result: **21 / 21 passed**.

### Important limitation

The old border rule is a detector for **isolated small border strips**. It is not a
general "anything long at the page edge is false" rule.

The newly observed giant edge strips can evade it because their area is not small
relative to their local neighbors. Therefore restoring this legacy rule fixes the
missing call-path parity, but it should not be claimed to solve every giant
page-edge strip. Those cases should be evaluated separately on train/validation,
likely using a physical-shape envelope such as border contact + border-parallel
elongation / thinness, rather than weakening the old rule in place.

## Legacy treasure audit

### HIGH: low-confidence structural-consensus recovery

Historical locations:

- `docs/history/2026-09-development/legacy-python/awnphen_legacy/postprocessing/reconstruction/low_confidence.py`
- `docs/history/2026-09-development/legacy-python/awnphen_legacy/postprocessing/reconstruction/low_confidence_stage.py`
- `archive/source_history/physical_closeout_20260925/completion/stages.py`

What it did:

- recovered missing proximal + distal evidence only when multiple overlapping
  low-confidence detections agreed structurally;
- required support from multiple lower and upper tiles and a unique qualifying
  cluster;
- used overlap, axis-angle and spatial-extension gates instead of trusting one
  low-confidence prediction.

Current status:

- Awn Studio still collects observations down to `SOURCE_OBSERVATION_FLOOR=0.05`
  and writes `lowconf/evidence_snapshot.json`;
- `physical_closeout.py` still accepts `lowconf_main_root` and
  `lowconf_tail_root`, but explicitly marks them legacy-only and does not use
  them in Unified Growth.

Assessment: **best treasure candidate**. The data are already being produced and
then discarded by the current physical route. A validation-only experiment should
test low-confidence evidence as an abstaining fallback for cases where the primary
support pool has a genuine gap. It should not be enabled globally without
validation because weak detections can also introduce background/grid fragments.

Priority: **HIGH, experiment next**.

---

### MEDIUM-HIGH: tile-boundary context

Historical location:

- `docs/history/2026-09-development/legacy-python/awnphen_legacy/modeling/inference/boundary_context.py`

What it did:

- distinguished true page-edge endpoints from sliding-window tile-edge endpoints;
- measured the endpoint's maximum interior distance inside its source tiles;
- emitted explicit states such as `boundary_clear`, `review_tile_edge`,
  `review_page_edge`, and `review_no_source_tile_context`.

Current status:

- current Unified Growth has geometric continuation and overlapping-tile evidence,
  but no direct `boundary_context` equivalent was found in `src/awnphen`.

Assessment: useful mostly as **diagnostic / ranking context**, not a hard rule.
A fragment terminating near a tile edge is exactly the type of evidence for which
growth should be more willing to seek continuation. Conversely, a true page-edge
termination should not trigger speculative extension.

Priority: **MEDIUM-HIGH**. Reintroduce first as inspection metadata or a soft feature,
then validate whether it improves continuation decisions.

---

### MEDIUM: terminal missing-representative rescue

Historical location:

- `docs/history/2026-09-development/legacy-python/awnphen_legacy/postprocessing/representative/missing_representative_rescue.py`

What it did:

- ran only after normal representative selection;
- touched only spikelets with no final representative;
- supported one narrow `review_far_base` failure;
- required mask-parent proximity, >=95% path retention, clear parent margin, and a
  unique eligible candidate;
- did not use phenotype GT.

Current status:

- current code records `missing_representative` as a failure state, but no
  equivalent terminal rescue implementation was found.

Assessment: attractive because it is **abstaining and terminal**, so it need not
perturb successful representatives. The old object model differs from Unified
Growth, so the implementation should not be copied literally. Its policy can be
recast as a fallback candidate check after branch selection.

Priority: **MEDIUM**.

---

### MEDIUM-LOW: reflection-gap rescue

Historical location:

- `docs/history/2026-09-development/legacy-python/awnphen_legacy/postprocessing/reconstruction/reflection_gap.py`

What it did:

- targeted reflective contamination / internal sharp-kink cases;
- removed a connected high-bend contamination region and tested whether the distal
  remainder became a plausible near-collinear continuation;
- was deliberately a narrow fallback after earlier reconstruction stages.

Current status:

- no active reflection-gap implementation exists in `src/awnphen`;
- Unified Growth already uses trajectory continuation, local-turn checks and a
  crossing guard.

Assessment: still scientifically interesting for the project's known reflective
gaps, but much of its geometry overlaps current growth logic. It is more valuable
as a **failure-mode-specific probe** than as an immediate production stage.

Priority: **MEDIUM-LOW**.

---

### LOW-MEDIUM: hidden-component / cross-instance recovery

Historical locations:

- `.../reconstruction/hidden_component.py`
- `.../reconstruction/cross_instance.py`

What they did:

- searched for disconnected components and neighboring instances that could
  continue the same physical trajectory.

Current status:

- Unified Growth's support pool, multi-hop continuation, morphology-guided ranking,
  ownership competition, and crossing guard now cover the same architectural
  problem more directly.

Assessment: mostly superseded. Individual metrics or test cases may still be useful
for diagnostics, but restoring these stages wholesale would create two competing
reconstruction systems.

Priority: **LOW-MEDIUM, mine tests/ideas rather than code**.

---

### LOW: legacy candidate deduplication

Historical location:

- `.../association/candidate_dedupe.py`

What it did:

- removed near-identical within-spikelet candidates;
- specially preferred a boundary-clear candidate over a shorter tile-edge partial
  duplicate.

Current status:

- Unified Growth performs conservative high-overlap awn compaction before support
  growth and then resolves sibling competition.

Assessment: largely superseded. The *tile-edge-aware preference* is the interesting
part and belongs with the boundary-context idea above, not as a second dedupe stage.

Priority: **LOW as a standalone port**.

---

### LOW: divider-continuation recovery

Historical locations:

- `.../reconstruction/divider_continuation.py`
- `.../reconstruction/divider_continuation_stage.py`

What it did:

- explicitly detected horizontal/vertical divider structures and searched for
  continuation across them.

Assessment: acquisition-specific and brittle. The current system should prefer
general evidence/trajectory reasoning rather than hard-coding document/grid
dividers.

Priority: **LOW**.

---

### DO NOT PORT: old representative ranking, orientation reassignment, old measurement closure

Historical areas:

- `postprocessing/representative/core.py`, `selection.py`,
  `orientation_reassignment.py`
- `measurement/closure.py`, `page_calibration.py`

Current equivalents are maintained and newer:

- spikelet-anchored orientation;
- morphology-guided growth + ownership + branch selection;
- crossing guard;
- root normalization with later apex rescue;
- resolution-aware grid calibration v2;
- calibrated DP1 measurement.

Assessment: direct port would regress architecture and create duplicate policy.

Priority: **DO NOT PORT**.

## Recommended order

1. Keep the restored legacy border diagnostic in Unified Growth premerge.
2. Run a dedicated train/validation review for the **giant** border-strip failure
   separately; do not pretend the old isolated-small gate covers it.
3. Prototype low-confidence structural-consensus recovery as an optional fallback.
4. Add tile-boundary context as inspection/soft evidence before considering a hard
   behavior change.
5. Evaluate terminal missing-representative rescue on validation-only failures.
6. Treat reflection-gap logic as a targeted experiment, not a default stage.
7. Leave the remaining legacy stages archived unless a concrete current failure
   points back to them.
