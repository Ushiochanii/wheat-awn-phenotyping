"""Stable single-image application service for Awn Studio.

This module owns the scientific orchestration needed by the Workbench while
keeping product/UI adaptation outside the scientific package. It intentionally
preserves the current production parameters and Unified Growth route.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PIL import Image
from shapely.geometry import mapping

from awnphen.phenotyping.detection.reconciliation import reconciliation_computation_cache

PAGE_ID = "image"

TILE_SIZE = 640
TILE_STRIDE = 320
MODEL_IMGSZ = 640
SOURCE_OBSERVATION_FLOOR = 0.05
PRIMARY_CONFIDENCE = 0.25
NMS_IOU = 0.7


@dataclass(frozen=True)
class WorkbenchPipelineResult:
    """Scientific artifacts produced for one Workbench source image."""

    width: int
    height: int
    tile_count: int
    source_sha256: str
    evidence: object
    reconciliation: object
    seeds: object
    cleanup: object
    closeout: dict[str, Path]
    inspection: dict
    phase2_root: Path
    phase3_root: Path
    seed_root: Path
    cleanup_root: Path
    lowconf_root: Path
    raw_masks: list[dict]
    reconciliation_awn_masks: list[dict]


@dataclass
class _StaticProvider:
    observations: tuple
    provenance: dict

    @property
    def provider(self):
        from awnphen.core.domain.physical import EvidenceProvider

        return EvidenceProvider.PRIMARY

    def provenance_payload(self):
        return self.provenance

    def observe_page(self, *, page_id: str):
        if page_id != PAGE_ID:
            raise ValueError(page_id)
        return self.observations


@reconciliation_computation_cache()
def run_workbench_pipeline(
    *,
    source: Path,
    workspace: Path,
    model,
    weights: Path,
    device: str,
    mm_per_px: float,
    progress: Callable,
    physical_closeout_runner=None,
    reconciliation_runner=None,
) -> WorkbenchPipelineResult:
    """Run the maintained scientific route for one Workbench image.

    Product-contract shaping deliberately stays in app/awn_studio.
    This function only owns scientific orchestration and its stable parameters.
    """
    from awnphen.core.io.evidence import write_evidence_snapshot
    from awnphen.core.io.reconciliation import write_reconciliation_result
    from awnphen.core.io.reconstruction import write_physical_seed_result
    from awnphen.core.io.spikelet_cleanup import write_spikelet_cleanup_result
    from awnphen.phenotyping.detection.acquisition import acquire_detection_evidence
    from awnphen.phenotyping.detection.adapter_provider import AdapterEvidenceProvider
    from awnphen.phenotyping.detection.providers import (
        PrimaryEvidenceProvider,
        sha256_file,
        tile_windows,
    )
    from awnphen.phenotyping.detection.reconciliation import (
        reconcile_detection_evidence,
    )
    from awnphen.phenotyping.physical.contracts import seed_physical_entities
    from awnphen.phenotyping.physical.spikelet_cleanup import (
        evaluate_physical_spikelet_cleanup,
    )
    from awnphen.pipeline.physical_closeout import run_physical_closeout

    source = Path(source)
    workspace = Path(workspace)
    weights = Path(weights)
    workspace.mkdir(parents=True, exist_ok=True)

    image_dir = workspace / "input"
    page_dir = workspace / "data" / "raw" / "primary"
    image_dir.mkdir(parents=True, exist_ok=True)
    page_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, image_dir / f"{PAGE_ID}.png")
    with Image.open(source) as image:
        width, height = image.size
        image.convert("RGB").save(page_dir / f"{PAGE_ID}.JPG", quality=95)

    tile_count = len(
        tile_windows(width, height, tile_size=TILE_SIZE, stride=TILE_STRIDE)
    )

    if hasattr(model, "predict_tile"):
        class ProgressAdapter:
            def __init__(self, delegate):
                self.delegate = delegate
                self.count = 0

            @property
            def architecture_name(self):
                return self.delegate.architecture_name

            @property
            def model_input_size(self):
                return self.delegate.model_input_size

            def provenance_payload(self):
                return self.delegate.provenance_payload()

            def predict_tile(self, image_bgr, *, confidence):
                result = self.delegate.predict_tile(
                    image_bgr,
                    confidence=confidence,
                )
                self.count += 1
                progress(
                    f"Running detection tile {self.count}/{tile_count}",
                    self.count,
                    stage="predicting",
                    total_tiles=tile_count,
                )
                return result

        provider = AdapterEvidenceProvider(
            adapter=ProgressAdapter(model),
            page_dir=image_dir,
            tile_size=TILE_SIZE,
            stride=TILE_STRIDE,
            confidence=SOURCE_OBSERVATION_FLOOR,
        )
    else:
        class ProgressModel:
            names = model.names
            count = 0

            def predict(self, *args, **kwargs):
                kwargs["device"] = device
                result = model.predict(*args, **kwargs)
                self.count += 1
                progress(
                    f"Running detection tile {self.count}/{tile_count}",
                    self.count,
                    stage="predicting",
                    total_tiles=tile_count,
                )
                return result

        provider = PrimaryEvidenceProvider(
            model=ProgressModel(),
            page_dir=image_dir,
            weights_path=weights,
            tile_size=TILE_SIZE,
            stride=TILE_STRIDE,
            model_imgsz=MODEL_IMGSZ,
            confidence=SOURCE_OBSERVATION_FLOOR,
            nms_iou=NMS_IOU,
            device=device,
        )
    all_observations = provider.observe_page(page_id=PAGE_ID)
    provenance = provider.provenance_payload()
    primary_provider = _StaticProvider(
        tuple(
            item
            for item in all_observations
            if item.confidence >= PRIMARY_CONFIDENCE
        ),
        {
            **provenance,
            "confidence": PRIMARY_CONFIDENCE,
            "source_observation_floor": SOURCE_OBSERVATION_FLOOR,
        },
    )
    low_provider = _StaticProvider(
        tuple(all_observations),
        {
            **provenance,
            "confidence": SOURCE_OBSERVATION_FLOOR,
            "role": "low_confidence_completion_evidence",
        },
    )

    source_sha = sha256_file(source)
    evidence = acquire_detection_evidence(
        page_id=PAGE_ID,
        source_sha256=source_sha,
        providers=(primary_provider,),
    )
    low_evidence = acquire_detection_evidence(
        page_id=PAGE_ID,
        source_sha256=source_sha,
        providers=(low_provider,),
    )

    phase2 = workspace / "phase2"
    low = workspace / "lowconf"
    (phase2 / PAGE_ID).mkdir(parents=True)
    (low / PAGE_ID).mkdir(parents=True)
    write_evidence_snapshot(evidence, phase2 / PAGE_ID / "evidence_snapshot.json")
    write_evidence_snapshot(
        low_evidence,
        low / PAGE_ID / "evidence_snapshot.json",
    )
    raw_masks = [
        {
            "id": str(item.evidence_id),
            "class_id": item.class_id,
            "confidence": float(item.confidence),
            "geometry": mapping(item.geometry),
        }
        for item in evidence.evidence
    ]
    progress(
        f"Detection complete. Reconciling {len(raw_masks)} evidence masks…",
        tile_count,
        preview={"stage": "raw", "layers": {"raw": raw_masks}},
        stage="reconciliation",
        total_tiles=tile_count,
    )

    reconcile = reconciliation_runner or reconcile_detection_evidence
    reconciliation = reconcile(evidence.evidence)
    phase3 = workspace / "phase3"
    (phase3 / PAGE_ID).mkdir(parents=True)
    write_reconciliation_result(
        reconciliation,
        phase3 / PAGE_ID / "reconciliation_result.json",
    )
    reconciliation_awn_masks = [
        {
            "id": str(item.hypothesis_id),
            "class_id": 0,
            "geometry": mapping(item.geometry),
        }
        for item in reconciliation.hypotheses
        if item.class_name == "awn"
    ]
    progress(
        (
            "Evidence reconciliation complete. Preparing "
            f"{len(reconciliation_awn_masks)} awn candidates…"
        ),
        tile_count,
        preview={
            "stage": "candidates",
            "layers": {"candidates": reconciliation_awn_masks},
        },
        stage="reconstruction",
        total_tiles=tile_count,
    )

    seeds = seed_physical_entities(reconciliation.hypotheses)
    seed_root = workspace / "seeds"
    (seed_root / PAGE_ID).mkdir(parents=True)
    write_physical_seed_result(
        seeds,
        seed_root / PAGE_ID / "physical_seed_result.json",
    )

    cleanup = evaluate_physical_spikelet_cleanup(
        seeds.physical_spikelets,
        evidence.evidence,
        page_width_px=width,
        page_height_px=height,
    )
    cleanup_root = workspace / "cleanup"
    (cleanup_root / PAGE_ID).mkdir(parents=True)
    write_spikelet_cleanup_result(
        cleanup,
        cleanup_root / PAGE_ID / "spikelet_cleanup_result.json",
    )

    period = 5.0 / float(mm_per_px)
    calibration = {
        PAGE_ID: {
            "x": period,
            "y": period,
            "adequate": True,
            "page_width_px": width,
            "page_height_px": height,
        }
    }
    progress(
        (
            "Running physical reconstruction, representative-awn selection, "
            "and root normalization…"
        ),
        tile_count,
        stage="physical_closeout",
        total_tiles=tile_count,
    )

    inspection_by_page: dict[str, dict] = {}
    closeout_runner = physical_closeout_runner or run_physical_closeout
    closeout = closeout_runner(
        repository_root=workspace,
        pages=(PAGE_ID,),
        phase2_root=phase2,
        phase3_root=phase3,
        seed_root=seed_root,
        cleanup_root=cleanup_root,
        lowconf_main_root=low,
        lowconf_tail_root=low,
        output_root=workspace / "closeout",
        calibration=calibration,
        inspection_sink=lambda page_id, payload: inspection_by_page.__setitem__(
            page_id,
            payload,
        ),
    )

    return WorkbenchPipelineResult(
        width=width,
        height=height,
        tile_count=tile_count,
        source_sha256=source_sha,
        evidence=evidence,
        reconciliation=reconciliation,
        seeds=seeds,
        cleanup=cleanup,
        closeout=closeout,
        inspection=inspection_by_page.get(PAGE_ID) or {},
        phase2_root=phase2,
        phase3_root=phase3,
        seed_root=seed_root,
        cleanup_root=cleanup_root,
        lowconf_root=low,
        raw_masks=raw_masks,
        reconciliation_awn_masks=reconciliation_awn_masks,
    )


__all__ = [
    "MODEL_IMGSZ",
    "NMS_IOU",
    "PAGE_ID",
    "PRIMARY_CONFIDENCE",
    "SOURCE_OBSERVATION_FLOOR",
    "TILE_SIZE",
    "TILE_STRIDE",
    "WorkbenchPipelineResult",
    "run_workbench_pipeline",
]
