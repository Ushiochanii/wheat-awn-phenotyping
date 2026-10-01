"""Canonical public model resolution.

The public release keeps model weights outside Git. A Hugging Face repository
will be configured before publication; local --weights remains supported for
offline development and reproducible testing.
"""
from __future__ import annotations

import os
from pathlib import Path

HF_MODEL_REPO = "anpanchanii/awnphen-yolo11n"
HF_MODEL_FILENAME = "best.pt"


def resolve_weights(explicit: str | Path | None = None) -> Path:
    if explicit:
        path = Path(explicit).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Model weights not found: {path}")
        return path

    env = os.environ.get("AWNPHEN_WEIGHTS")
    if env:
        path = Path(env).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f"AWNPHEN_WEIGHTS does not exist: {path}")
        return path

    if HF_MODEL_REPO.startswith("TODO_"):
        raise RuntimeError(
            "Canonical model repository is not configured yet. "
            "For local staging, pass --weights PATH or set AWNPHEN_WEIGHTS."
        )

    try:
        from huggingface_hub import hf_hub_download
    except ImportError as error:
        raise RuntimeError(
            "The huggingface-hub dependency is missing. Reinstall AwnPhen with its runtime dependencies."
        ) from error

    return Path(hf_hub_download(repo_id=HF_MODEL_REPO, filename=HF_MODEL_FILENAME))
