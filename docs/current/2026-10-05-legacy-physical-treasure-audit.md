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

## Unified border-artifact cleanup

The historical small-border rule and the newer giant-border failure are now handled
by one geometry-only evaluator in:

- `src/awnphen/phenotyping/physical/spikelet_cleanup.py`
- implementation label: `border_following_v3`

The final rule no longer depends on candidate size, local-neighbour status, or an
"extreme strip" category:

```text
touch page border
AND major axis is parallel to that border (<= 15°)
AND >= 60% of the candidate's longitudinal span stays inside a narrow edge band
```

The edge band is resolution-aware: `max(4 px, 0.2% of the shorter page dimension)`.
The overlap metric is longitudinal rather than area-based, so a thin and a thick
border strip are treated consistently. A normal spikelet that only touches the
border at a tip or short segment is retained.

Replaying the new rule over all 4,273 train+validation human spikelet annotations
rejected **0 / 4,273** GT spikelets. In this corpus, no true spikelet simultaneously
touched the page edge and had its minimum-rotated-rectangle major axis within 15°
of that edge, leaving a wide safety margin for the 60% following-fraction gate.

The same evaluator is used by both the physical cleanup record and Unified Growth
premerge, so small and giant page-edge artifacts now share exactly one rule.

The Unified Growth call path receives page dimensions before orientation, seed
discovery and growth. Existing independent filters remain:

- `tiny_area`: area < 10 mm²;
- `awn_overlap_contamination`;
- `oversized_area_and_length`: area > 250 mm² AND calibrated major axis > 45 mm;
- fragment attachment.

Focused regression tests after the unified change:

- spikelet premerge, including small-border, giant-border and normal-border cases;
- Unified Growth;
- Workbench pipeline service.

Result: **23 / 23 passed**.

## Legacy treasure audit

### Low-confidence logic: partly already absorbed by Unified Growth

Historical locations:

- `docs/history/2026-09-development/legacy-python/awnphen_legacy/postprocessing/reconstruction/low_confidence.py`
- `docs/history/2026-09-development/legacy-python/awnphen_legacy/postprocessing/reconstruction/low_confidence_stage.py`

The old route had a distinct low-confidence rescue stage based on repeated
cross-tile structural consensus. That exact stage is **not** active now, but its
core idea was partly absorbed into Unified Growth:

- Awn supports retain prediction confidence in `growth/supports.py`;
- morphology-guided continuation uses confidence directly in the association gain:
  `confidence * log1p(extension / scale) - geometric_energy`;
- highly overlapping detections are compacted before growth into a shared support
  hypothesis, preserving the strongest member confidence and union geometry.

This is similar in spirit, but it is not the old multi-tile consensus test: the
current default ranker does not require multiple low-confidence tiles to agree
before admitting a support.

There is one important boundary: the normal Workbench physical route is built from
the primary evidence snapshot, filtered at `PRIMARY_CONFIDENCE=0.25`. The
additional 0.05--0.25 observations are still written to
`lowconf/evidence_snapshot.json`, but `physical_closeout.py` does not feed that
separate snapshot into Unified Growth.

Therefore the correct conclusion is not "Unified Growth has no low-confidence
logic." It **does** have confidence-aware evidence ranking and overlap-based support
fusion. What it does not currently have is the old special rescue mechanism that
allows sub-primary-threshold evidence back in only after multi-tile structural
consensus.

Decision for now: **do not port the old low-confidence consensus stage**. It would
duplicate a substantial part of the current confidence-aware Growth design. Keep the
old implementation archived; revisit only if a validation failure is specifically
shown to require evidence in the 0.05--0.25 band.

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
