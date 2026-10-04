# Developer architecture note

Awn Studio separates image recognition from physical reconstruction and measurement.

```text
digitized spikelet image
  -> instance segmentation
  -> awn reconstruction
  -> representative awn selection
  -> skeleton / centerline extraction
  -> calibrated centerline measurement
  -> human review and export
```

## Where things live

- `src/awnphen/modeling/` — model inference and prediction adapters
- `src/awnphen/phenotyping/physical/` — reconstruction of physical awn structure
- `src/awnphen/phenotyping/measurement/` — centerline, root normalization, calibration, and length measurement
- `src/awnphen/pipeline/` — maintained scientific orchestration
- `app/awn_studio/` — public review/edit/export interface

## Design boundaries

Segmentation masks are evidence, not final measurements. Length is measured from the reconstructed centerline rather than directly from a mask.

The scientific runtime should remain separate from product-specific UI behavior. Manual review may change the accepted result, but it should not silently rewrite the original automatic evidence.

The public repository contains the maintained runtime needed to use Awn Studio. Research datasets, comparison checkpoints, training history, benchmark workspaces, and publication working files stay outside the public package.

The public release ships a default segmentation checkpoint for reproducibility, but the measurement workflow itself should not be described as a single-model method.
