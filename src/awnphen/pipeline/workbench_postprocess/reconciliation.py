"""Frozen Awn Studio reconciliation policy promoted from the validated twin."""
from __future__ import annotations

from awnphen.phenotyping.detection.reconciliation import (
    ReconciliationConfig,
    reconcile_detection_evidence as _production_reconcile,
)


CROSS_TILE_AWN_MAX_AXIS_ANGLE_DEG = 12.0
EXPERIMENT_ID = f"cross-tile-global-axis-{CROSS_TILE_AWN_MAX_AXIS_ANGLE_DEG:g}deg"


def reconcile_detection_evidence(evidence):
    """Run Awn Studio reconciliation with the frozen global awn axis gate."""
    config = ReconciliationConfig(
        cross_tile_awn_max_axis_angle_deg=CROSS_TILE_AWN_MAX_AXIS_ANGLE_DEG,
    )
    return _production_reconcile(evidence, config=config)


__all__ = [
    "CROSS_TILE_AWN_MAX_AXIS_ANGLE_DEG",
    "EXPERIMENT_ID",
    "reconcile_detection_evidence",
]
