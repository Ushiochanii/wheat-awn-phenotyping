"""Reusable stages for tiled whole-page inference."""

from __future__ import annotations

import base64
from dataclasses import asdict
import json
from pathlib import Path
from typing import Any

import cv2

from awnphen.modeling.inference.merge import dedupe, stitch_awns
from awnphen.modeling.inference.predictor import (
    MERGE,
    merge,
    predict,
    save_overlay,
    serialize,
)
from awnphen.modeling.inference.tiling import sha, windows


def prepare_page_image(
    source: str | Path,
    config,
) -> tuple[Any, list[tuple[int, int, int, int]], int]:
    """Load one page and build the frozen overlapping tile schedule."""

    source = Path(source)
    image = cv2.imread(str(source))
    if image is None:
        raise FileNotFoundError(source)

    height, width = image.shape[:2]
    tiles = windows(
        width,
        height,
        config.tile_size,
        config.stride,
    )
    model_imgsz = int(config.model_imgsz or config.tile_size)
    return image, tiles, model_imgsz


def predict_page_tiles(
    model,
    image,
    tiles,
    *,
    model_imgsz: int,
):
    """Run instance segmentation independently on every overlapping tile."""

    return predict(
        model,
        image,
        tiles,
        model_imgsz,
    )


def merge_tile_predictions(raw):
    """Restore tile predictions to page coordinates and merge same-instance overlaps."""

    return merge(raw)


def deduplicate_page_instances(
    first_stage,
    *,
    config,
):
    """Deduplicate awns and spikelets with their class-specific frozen rules."""

    awns = [
        item
        for item in first_stage
        if item["class_id"] == 0
    ]
    spikelets = [
        item
        for item in first_stage
        if item["class_id"] == 1
    ]

    spikelets, spikelet_merges = dedupe(
        spikelets,
        config.spikelet_duplicate_iou,
        config.spikelet_duplicate_overlap,
        config.spikelet_duplicate_buffer,
        forbid_shared_tiles=False,
    )
    awns, awn_duplicate_merges = dedupe(
        awns,
        config.duplicate_iou,
        config.duplicate_overlap,
        config.duplicate_buffer,
        forbid_shared_tiles=True,
        shared_tile_max_axis_angle=config.shared_tile_max_axis_angle,
        shared_tile_min_overlap=config.shared_tile_min_overlap,
    )
    return (
        awns,
        spikelets,
        awn_duplicate_merges,
        spikelet_merges,
    )


def stitch_page_awn_fragments(
    awns,
    spikelets,
    *,
    config,
):
    """Join geometrically compatible awn fragments without using ground truth."""

    return stitch_awns(
        awns,
        spikelets,
        config,
    )


def finalize_page_predictions(
    awns,
    spikelets,
    *,
    config,
):
    """Apply the frozen final awn-confidence threshold and combine classes."""

    awns = [
        item
        for item in awns
        if float(item.get("confidence", 0.0))
        >= config.awn_final_confidence
    ]
    return awns, awns + spikelets


def build_page_inference_result(
    *,
    page: str,
    source: str | Path,
    weights: str | Path,
    config,
    model_imgsz: int,
    tiles,
    raw,
    first_stage,
    first_edges,
    final,
    final_awns,
    spikelets,
    awn_duplicate_merges,
    spikelet_merges,
    endpoint_joins,
    inference_seconds: float,
) -> dict[str, Any]:
    """Build the stable results.json payload for one page."""

    source = Path(source)
    weights = Path(weights)
    return {
        "page": page,
        "ground_truth_used": False,
        "frozen_parameters_changed_for_page": False,
        "weights": str(weights),
        "weights_sha256": sha(weights),
        "source": str(source),
        "source_sha256": sha(source),
        "input_size": config.tile_size,
        "model_imgsz": model_imgsz,
        "stride": config.stride,
        "confidence_inference": 0.25,
        "nms_iou": 0.7,
        "first_stage_merge": MERGE,
        "frozen_postprocess": asdict(config),
        "tile_count": len(tiles),
        "raw_prediction_count": len(raw),
        "first_stage_prediction_count": len(first_stage),
        "final_prediction_count": len(final),
        "final_awn_count": len(final_awns),
        "final_spikelet_count": len(spikelets),
        "awn_duplicate_merges": len(awn_duplicate_merges),
        "spikelet_duplicate_merges": len(spikelet_merges),
        "awn_endpoint_joins": len(endpoint_joins),
        "inference_seconds": float(inference_seconds),
        "first_stage_predictions": serialize(first_stage),
        "predictions": serialize(final),
        "first_stage_merge_edges": first_edges,
        "awn_duplicate_merge_records": awn_duplicate_merges,
        "spikelet_duplicate_merge_records": spikelet_merges,
        "awn_endpoint_join_records": endpoint_joins,
    }


def _html_image(path: Path) -> str:
    encoded = base64.b64encode(path.read_bytes()).decode()
    return (
        "<img src='data:image/jpeg;base64,"
        + encoded
        + "' style='max-width:100%'>"
    )


def write_page_inference_artifacts(
    *,
    image,
    first_stage,
    final,
    result: dict[str, Any],
    output_root: str | Path,
) -> Path:
    """Write overlays, results.json and the human-readable page report."""

    output_root = Path(output_root)
    page_dir = output_root / str(result["page"])
    page_dir.mkdir(
        parents=True,
        exist_ok=False,
    )

    save_overlay(
        image,
        first_stage,
        page_dir / "before_postprocess.jpg",
    )
    save_overlay(
        image,
        final,
        page_dir / "after_postprocess.jpg",
    )

    (page_dir / "results.json").write_text(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    summary_keys = (
        "page",
        "tile_count",
        "raw_prediction_count",
        "first_stage_prediction_count",
        "final_prediction_count",
        "final_awn_count",
        "final_spikelet_count",
        "awn_duplicate_merges",
        "spikelet_duplicate_merges",
        "awn_endpoint_joins",
        "inference_seconds",
    )
    report_summary = {
        key: result[key]
        for key in summary_keys
    }
    report = f"""<!doctype html><html lang='en'><meta charset='utf-8'>
<style>body{{font:16px/1.6 system-ui;max-width:1250px;margin:30px auto;padding:0 22px}}pre{{white-space:pre-wrap;background:#f5f6f4;padding:14px}}img{{max-width:100%}}</style>
<h1>Frozen sliding-window inference: {result['page']}</h1>
<p>No ground truth is loaded or used. Parameters are frozen from validation.</p>
<pre>{json.dumps(report_summary, ensure_ascii=False, indent=2)}</pre>
<h2>Before postprocess</h2>{_html_image(page_dir / 'before_postprocess.jpg')}
<h2>After postprocess</h2>{_html_image(page_dir / 'after_postprocess.jpg')}
<h2>Frozen parameters</h2><pre>{json.dumps(result['frozen_postprocess'], ensure_ascii=False, indent=2)}</pre>
</html>"""
    (page_dir / "report.html").write_text(
        report,
        encoding="utf-8",
    )
    return page_dir


__all__ = [
    "prepare_page_image",
    "predict_page_tiles",
    "merge_tile_predictions",
    "deduplicate_page_instances",
    "stitch_page_awn_fragments",
    "finalize_page_predictions",
    "build_page_inference_result",
    "write_page_inference_artifacts",
]
