"""Maintained Workbench policy with the 2026-10-02 crossing guard.

The Workbench retains its 2026-09-30 bridge and seed checks and delegates crossing
routing to the maintained physical growth package. Historical frozen benchmark
records and source snapshots retain their original provenance.
"""

from .postprocess import run_physical_closeout
from .reconciliation import reconcile_detection_evidence

WORKBENCH_POSTPROCESS_VERSION = "awn-studio-postprocess-crossing-20261002"

__all__ = [
    "WORKBENCH_POSTPROCESS_VERSION",
    "reconcile_detection_evidence",
    "run_physical_closeout",
]
