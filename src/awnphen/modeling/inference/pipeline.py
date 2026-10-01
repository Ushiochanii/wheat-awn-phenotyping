"""Frozen whole-page inference compatibility pipeline.

Reusable stage implementations live in awnphen.modeling.inference.stages.
This module keeps the frozen scientific configuration and the compact
run_frozen_page() API used by evaluation code.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import time

import yaml

from awnphen.modeling.inference.stages import (
    build_page_inference_result,
    deduplicate_page_instances,
    finalize_page_predictions,
    merge_tile_predictions,
    predict_page_tiles,
    prepare_page_image,
    stitch_page_awn_fragments,
    write_page_inference_artifacts,
)


@dataclass(frozen=True, slots=True)
class FrozenInferenceConfig:
    tile_size: int = 640
    stride: int = 320
    # Network raster size is intentionally separable from source-page FOV.
    # None preserves the historical contract: model imgsz == source tile size.
    model_imgsz: int | None = None
    duplicate_iou: float = 0.28
    duplicate_overlap: float = 0.62
    duplicate_buffer: float = 3.0
    shared_tile_max_axis_angle: float = 1.5
    shared_tile_min_overlap: float = 0.94
    awn_final_confidence: float = 0.50
    spikelet_duplicate_iou: float = 0.30
    spikelet_duplicate_overlap: float = 0.65
    spikelet_duplicate_buffer: float = 2.0
    anchor_distance: float = 55.0
    max_gap: float = 70.0
    max_tangent_angle: float = 22.0
    max_connector_angle: float = 26.0
    max_width_ratio: float = 2.8
    minimum_join_score: float = 0.54



PROJECT_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_FROZEN_CONFIG = (
    PROJECT_ROOT / "configs/inference/frozen_sliding_window_v1.yaml"
)


def load_frozen_inference_config(
    path: str | Path = DEFAULT_FROZEN_CONFIG,
) -> FrozenInferenceConfig:
    """Load the frozen inference YAML without changing historical semantics."""

    path = Path(path)
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    model = payload["model"]
    tiling = payload["tiling"]
    postprocess = payload["postprocess"]

    # These two values remain fixed inside the historical predictor API.
    # Reject a config that claims otherwise instead of pretending they are tunable.
    if float(model["confidence"]) != 0.25:
        raise ValueError("frozen inference confidence must remain 0.25")
    if float(model["nms_iou"]) != 0.7:
        raise ValueError("frozen inference NMS IoU must remain 0.7")

    tile_size = int(tiling["tile_size"])
    model_input_size = int(model["input_size"])
    model_imgsz = (
        None
        if model_input_size == tile_size
        else model_input_size
    )

    return FrozenInferenceConfig(
        tile_size=tile_size,
        stride=int(tiling["stride"]),
        model_imgsz=model_imgsz,
        duplicate_iou=float(postprocess["duplicate_iou"]),
        duplicate_overlap=float(postprocess["duplicate_overlap"]),
        duplicate_buffer=float(postprocess["duplicate_buffer"]),
        shared_tile_max_axis_angle=float(
            postprocess["shared_tile_max_axis_angle"]
        ),
        shared_tile_min_overlap=float(
            postprocess["shared_tile_min_overlap"]
        ),
        awn_final_confidence=float(
            postprocess["awn_final_confidence"]
        ),
        spikelet_duplicate_iou=float(
            postprocess["spikelet_duplicate_iou"]
        ),
        spikelet_duplicate_overlap=float(
            postprocess["spikelet_duplicate_overlap"]
        ),
        spikelet_duplicate_buffer=float(
            postprocess["spikelet_duplicate_buffer"]
        ),
        anchor_distance=float(postprocess["anchor_distance"]),
        max_gap=float(postprocess["max_gap"]),
        max_tangent_angle=float(
            postprocess["max_tangent_angle"]
        ),
        max_connector_angle=float(
            postprocess["max_connector_angle"]
        ),
        max_width_ratio=float(postprocess["max_width_ratio"]),
        minimum_join_score=float(
            postprocess["minimum_join_score"]
        ),
    )


FROZEN = load_frozen_inference_config()


def run_frozen_page(
    model,
    page: str,
    source: Path,
    output: Path,
    weights: Path,
    *,
    config: FrozenInferenceConfig = FROZEN,
) -> dict:
    """Run one page through the frozen prediction-only pipeline.

    This compatibility API deliberately uses the same reusable stage functions
    as scripts/pipeline/run_tiled_inference.py.
    """

    image, tiles, model_imgsz = prepare_page_image(
        source,
        config,
    )

    started = time.time()

    raw = predict_page_tiles(
        model,
        image,
        tiles,
        model_imgsz=model_imgsz,
    )

    first_stage, first_edges = merge_tile_predictions(raw)

    (
        awns,
        spikelets,
        awn_duplicate_merges,
        spikelet_merges,
    ) = deduplicate_page_instances(
        first_stage,
        config=config,
    )

    awns, endpoint_joins = stitch_page_awn_fragments(
        awns,
        spikelets,
        config=config,
    )

    final_awns, final = finalize_page_predictions(
        awns,
        spikelets,
        config=config,
    )
    seconds = time.time() - started

    result = build_page_inference_result(
        page=page,
        source=source,
        weights=weights,
        config=config,
        model_imgsz=model_imgsz,
        tiles=tiles,
        raw=raw,
        first_stage=first_stage,
        first_edges=first_edges,
        final=final,
        final_awns=final_awns,
        spikelets=spikelets,
        awn_duplicate_merges=awn_duplicate_merges,
        spikelet_merges=spikelet_merges,
        endpoint_joins=endpoint_joins,
        inference_seconds=seconds,
    )

    write_page_inference_artifacts(
        image=image,
        first_stage=first_stage,
        final=final,
        result=result,
        output_root=output,
    )
    return result


__all__ = [
    "FrozenInferenceConfig",
    "DEFAULT_FROZEN_CONFIG",
    "load_frozen_inference_config",
    "FROZEN",
    "run_frozen_page",
]
