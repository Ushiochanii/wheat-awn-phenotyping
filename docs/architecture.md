# Runtime architecture

```text
scanned image
  -> tiled YOLO11N segmentation (640 px, stride 320)
  -> detection evidence
  -> reconciliation and spikelet cleanup
  -> Unified Growth physical reconstruction
  -> representative awn selection
  -> root normalization
  -> calibrated path length
  -> Awn Studio review/edit/export
```

Awn Studio is the product layer. Scientific decisions remain in the `awnphen` runtime. Manual editing changes the reviewed result without rewriting the saved automatic evidence.
