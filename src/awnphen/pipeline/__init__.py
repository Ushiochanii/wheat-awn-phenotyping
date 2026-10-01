"""Maintained pipeline orchestration.

Unified Growth v1 is the only maintained physical closeout route. Historical
closeout implementations live under archive/source_history/ and are deliberately
not exported from the production package.
"""
from .physical_closeout import run_physical_closeout
from .workbench import PAGE_ID as WORKBENCH_PAGE_ID, run_workbench_pipeline

__all__ = [
    "WORKBENCH_PAGE_ID",
    "run_physical_closeout",
    "run_workbench_pipeline",
]
