"""Frozen Awn Studio post-processing adapter promoted from the validated twin."""
from __future__ import annotations

from awnphen.pipeline.physical_closeout import (
    run_physical_closeout as _run_production_closeout,
)

from .growth_pipeline import EXPERIMENT_ID, run_page


def run_physical_closeout(**kwargs):
    """Reuse the maintained closeout shell while swapping the page algorithm."""
    return _run_production_closeout(
        **kwargs,
        page_runner=run_page,
    )


__all__ = ["EXPERIMENT_ID", "run_physical_closeout"]
