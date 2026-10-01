# Crossing-aware runtime update

The default algorithm is now `awn-studio-postprocess-crossing-20261002`. Both
the Python runtime and Awn Studio call the maintained crossing logic in
`src/awnphen/phenotyping/physical/growth/crossing.py`.

The guard identifies crossings in the union of unmodified model masks, splits
support trajectories, and checks incoming/outgoing arm correspondence at 1.5,
2 and 3 mm tangent scales. It follows observed skeleton nodes through a
resolvable crossing. Existing geometry and ownership checks still apply.
Sharp unresolved junctions and entry into another spikelet can terminate growth.
An ambiguous crossing may stop conservatively and require human review.

The readable app and wheel bundle contain the same backend and review logic.
`GET /api/model` exposes `pipeline_version` and `crossing_guard_enabled`.
Refresh Studio and rerun the image to obtain updated measurements. Previous
results and manual edits are not automatically replaced.

Before public synchronization, the maintained implementation reproduced all
310 representative paths on 11 previously reviewed validation-cache pages,
including the 13 reviewed changes; detection evidence remained unchanged.
This is migration equivalence evidence, not a new ground-truth accuracy claim.

The canonical model binding, external weight distribution, public job storage
and optional scale probe retain their installation-specific adaptations.
Root normalization now uses the maintained 5 mm minimum-path default; the
minimum spikelet area remains 10 mm².

## Verify

Run from the repository root after installing development dependencies:

```bash
python -m pytest tests -q
node --test tests/browser/*.test.mjs
```

The tests cover crossing direction, observed-mask routing, junction clipping,
ownership, inspection replay, Studio contracts, review, persistence and export.
