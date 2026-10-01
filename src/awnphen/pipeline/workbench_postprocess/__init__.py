"""Frozen Workbench post-processing policy promoted from the 2026-09-30 twin.

This package intentionally scopes the promoted policy to Awn Studio. It does not
change the historical 2026-09-25 canonical pipeline defaults used by frozen
benchmark records.
"""

from .postprocess import run_physical_closeout
from .reconciliation import reconcile_detection_evidence

WORKBENCH_POSTPROCESS_VERSION = "awn-studio-postprocess-20260930"

__all__ = [
    "WORKBENCH_POSTPROCESS_VERSION",
    "reconcile_detection_evidence",
    "run_physical_closeout",
]
