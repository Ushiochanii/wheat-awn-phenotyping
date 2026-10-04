"""Canonical public model resolution.

The public release keeps model weights outside Git. The default checkpoint is
pinned to a specific Hugging Face revision and verified by SHA-256 so a given
AwnPhen release cannot silently drift to a different model.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil

HF_MODEL_REPO = "anpanchanii/awnphen-yolo11n"
HF_MODEL_FILENAME = "best.pt"
HF_MODEL_REVISION = "7622e142fd3ab720c19f9ed1de085f998eb8c2e6"
HF_MODEL_SHA256 = "a7a5cf23bf5d35266e4fa6b1dc0244ee802026a381548bcd202f04b3ebf42097"
CANONICAL_MODEL_DIR = Path.home() / ".cache" / "awn-studio" / "models" / "yolo11n-canonical"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def resolve_weights(explicit: str | Path | None = None) -> Path:
    if explicit:
        path = Path(explicit).expanduser()
        if not path.is_file():
            raise FileNotFoundError(f"Model weights not found: {path}")
        return path

    env = os.environ.get("AWNPHEN_WEIGHTS")
    if env:
        path = Path(env).expanduser()
        if not path.is_file():
            raise FileNotFoundError(f"AWNPHEN_WEIGHTS does not exist: {path}")
        return path

    try:
        from huggingface_hub import hf_hub_download
    except ImportError as error:
        raise RuntimeError(
            "The huggingface-hub dependency is missing. "
            "Reinstall AwnPhen with its runtime dependencies."
        ) from error

    path = Path(
        hf_hub_download(
            repo_id=HF_MODEL_REPO,
            filename=HF_MODEL_FILENAME,
            revision=HF_MODEL_REVISION,
        )
    )
    actual = _sha256(path)
    if actual != HF_MODEL_SHA256:
        raise RuntimeError(
            "Canonical model checksum mismatch: "
            f"expected {HF_MODEL_SHA256}, got {actual}."
        )

    # Hugging Face may return a content-addressed blob path whose filename is
    # only a SHA-256 digest. Ultralytics infers model format from the suffix,
    # so always expose the canonical checkpoint through a stable .pt path.
    if path.suffix.lower() == ".pt":
        return path

    CANONICAL_MODEL_DIR.mkdir(parents=True, exist_ok=True)
    materialized = CANONICAL_MODEL_DIR / HF_MODEL_FILENAME
    if not materialized.is_file() or _sha256(materialized) != HF_MODEL_SHA256:
        temporary = materialized.with_suffix(".pt.tmp")
        shutil.copy2(path, temporary)
        temporary.replace(materialized)
    return materialized
