"""Canonical YOLO11N model backend for the public Awn Studio release."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
DEFAULT_MODEL_ID = "yolo11n-canonical"


@dataclass(frozen=True)
class ModelSpec:
    id: str
    name: str
    weights: Path
    adapter: str = "ultralytics_yolo_seg"
    description: str = "Canonical YOLO11N model for wheat awn phenotyping."

    @property
    def available(self) -> bool:
        return self.weights.is_file()

    def public(self, *, default: bool = False) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "adapter": self.adapter,
            "description": self.description,
            "available": self.available,
            "default": default,
        }


def _weights_path() -> Path:
    configured = os.environ.get("AWNPHEN_WEIGHTS")
    if configured:
        return Path(configured).expanduser().resolve()
    try:
        from awnphen.model import resolve_weights
        return resolve_weights()
    except RuntimeError:
        return ROOT / "models" / "best.pt"


def model_spec(model_id: str | None = None) -> ModelSpec:
    requested = model_id or DEFAULT_MODEL_ID
    if requested != DEFAULT_MODEL_ID:
        raise ValueError(f"Unknown model: {requested}")
    return ModelSpec(
        id=DEFAULT_MODEL_ID,
        name="YOLO11N · Canonical",
        weights=_weights_path(),
    )


def model_catalog() -> list[dict]:
    return [model_spec().public(default=True)]


DEFAULT_MODEL = model_spec()
MODEL_REGISTRY = {DEFAULT_MODEL_ID: DEFAULT_MODEL}
MODEL_NAME = DEFAULT_MODEL.name
WEIGHTS = DEFAULT_MODEL.weights


class Engine:
    """Lazy single-model inference engine used by Awn Studio."""

    def __init__(self, device="cpu", *, physical_closeout_runner=None, reconciliation_runner=None):
        self.device = device
        self.physical_closeout_runner = physical_closeout_runner
        self.reconciliation_runner = reconciliation_runner
        self.model = None
        self.loaded_weights = None

    def _load_model(self, spec: ModelSpec):
        if not spec.available:
            raise FileNotFoundError(
                f"Canonical model weights not found: {spec.weights}. "
                "Pass --weights, set AWNPHEN_WEIGHTS, or configure the Hugging Face model."
            )
        if self.model is not None and self.loaded_weights == spec.weights:
            return self.model
        from ultralytics import YOLO
        model = YOLO(str(spec.weights))
        if dict(model.names) != {0: "awn", 1: "spikelet"}:
            raise ValueError(f"Model class mapping mismatch: {model.names}")
        self.model = model
        self.loaded_weights = spec.weights
        return model

    def run(self, source, output, progress, *, mm_per_px, model_id=None):
        from canonical_backend import run_canonical
        spec = model_spec(model_id)
        progress(f"Loading {spec.name}…", 0, stage="loading")
        model = self._load_model(spec)
        return run_canonical(
            source=source,
            output=output,
            model=model,
            weights=spec.weights,
            model_name=spec.name,
            model_id=spec.id,
            device=self.device,
            mm_per_px=mm_per_px,
            progress=progress,
            physical_closeout_runner=self.physical_closeout_runner,
            reconciliation_runner=self.reconciliation_runner,
        )


__all__ = [
    "DEFAULT_MODEL", "DEFAULT_MODEL_ID", "Engine", "MODEL_NAME",
    "MODEL_REGISTRY", "ModelSpec", "ROOT", "WEIGHTS", "model_catalog", "model_spec",
]
