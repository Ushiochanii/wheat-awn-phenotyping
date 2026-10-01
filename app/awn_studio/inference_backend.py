"""Canonical YOLO11N backend with optional user-added YOLO segmentation checkpoints."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import hashlib
import json
import os
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
DEFAULT_MODEL_ID = "yolo11n-canonical"
CUSTOM_MODELS_PATH = Path(
    os.environ.get("AWN_STUDIO_CUSTOM_MODELS", Path.home() / ".config/awn-studio/models.json")
).expanduser()
SUPPORTED_ADAPTERS = {"ultralytics_yolo_seg": "Ultralytics YOLO segmentation"}


@dataclass(frozen=True)
class ModelSpec:
    id: str
    name: str
    weights: Path
    adapter: str = "ultralytics_yolo_seg"
    description: str = "Canonical YOLO11N model for wheat awn phenotyping."
    custom: bool = False

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
            "custom": self.custom,
            "weights": str(self.weights) if self.custom else None,
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


def _normalize_model_path(value: str | Path) -> Path:
    raw = str(value).strip().strip('"').replace("\\", "/")
    raw = re.sub(r"/+", "/", raw)
    match = re.match(r"^([A-Za-z]):/(.*)$", raw)
    if match and Path("/mnt").is_dir():
        drive, rest = match.groups()
        raw = f"/mnt/{drive.lower()}/{rest}"
    return Path(raw).expanduser().resolve()


def _read_custom_models() -> list[dict]:
    try:
        data = json.loads(CUSTOM_MODELS_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    except Exception:
        return []
    return data if isinstance(data, list) else []


def _write_custom_models(items: list[dict]) -> None:
    CUSTOM_MODELS_PATH.parent.mkdir(parents=True, exist_ok=True)
    CUSTOM_MODELS_PATH.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def _canonical_spec() -> ModelSpec:
    return ModelSpec(
        id=DEFAULT_MODEL_ID,
        name="YOLO11N · Canonical",
        weights=_weights_path(),
    )


def _custom_specs() -> tuple[ModelSpec, ...]:
    specs = []
    for item in _read_custom_models():
        try:
            adapter = str(item.get("adapter") or "ultralytics_yolo_seg")
            if adapter not in SUPPORTED_ADAPTERS:
                continue
            specs.append(ModelSpec(
                id=str(item["id"]),
                name=str(item["name"]),
                weights=_normalize_model_path(item["weights"]),
                adapter=adapter,
                description=str(item.get("description") or "User-added local model."),
                custom=True,
            ))
        except Exception:
            continue
    return tuple(specs)


def refresh_model_registry() -> dict[str, ModelSpec]:
    canonical = _canonical_spec()
    registry = {canonical.id: canonical}
    for spec in _custom_specs():
        if spec.id not in registry:
            registry[spec.id] = spec
    MODEL_REGISTRY.clear()
    MODEL_REGISTRY.update(registry)
    return MODEL_REGISTRY


def register_custom_model(*, name: str, weights: str, adapter: str = "ultralytics_yolo_seg", description: str = "") -> ModelSpec:
    name = str(name).strip()
    if not name:
        raise ValueError("Model name is required.")
    adapter = str(adapter).strip()
    if adapter not in SUPPORTED_ADAPTERS:
        raise ValueError(f"Unsupported model adapter: {adapter}")
    path = _normalize_model_path(weights)
    digest = hashlib.sha1(f"{adapter}|{path}".encode()).hexdigest()[:10]
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "model"
    model_id = f"custom-{slug[:32]}-{digest}"
    items = [item for item in _read_custom_models() if item.get("id") != model_id]
    items.append({
        "id": model_id,
        "name": name,
        "weights": str(path),
        "adapter": adapter,
        "description": str(description or ""),
    })
    _write_custom_models(items)
    refresh_model_registry()
    return MODEL_REGISTRY[model_id]


def remove_custom_model(model_id: str) -> bool:
    items = _read_custom_models()
    kept = [item for item in items if item.get("id") != model_id]
    if len(kept) == len(items):
        return False
    _write_custom_models(kept)
    refresh_model_registry()
    return True


MODEL_REGISTRY: dict[str, ModelSpec] = {}
refresh_model_registry()
DEFAULT_MODEL = MODEL_REGISTRY[DEFAULT_MODEL_ID]
MODEL_NAME = DEFAULT_MODEL.name
WEIGHTS = DEFAULT_MODEL.weights


def model_catalog() -> list[dict]:
    refresh_model_registry()
    return [
        spec.public(default=spec.id == DEFAULT_MODEL_ID)
        for spec in MODEL_REGISTRY.values()
    ]


def model_spec(model_id: str | None = None) -> ModelSpec:
    refresh_model_registry()
    requested = model_id or DEFAULT_MODEL_ID
    try:
        return MODEL_REGISTRY[requested]
    except KeyError as error:
        raise ValueError(f"Unknown model: {requested}") from error


class Engine:
    """Lazy single-active-model cache used by Awn Studio."""

    def __init__(self, device="cpu", *, physical_closeout_runner=None, reconciliation_runner=None):
        self.device = device
        self.physical_closeout_runner = physical_closeout_runner
        self.reconciliation_runner = reconciliation_runner
        self.model = None
        self.model_id = None
        self.loaded_weights = None

    def _load_model(self, spec: ModelSpec):
        if not spec.available:
            raise FileNotFoundError(
                f"Model weights not found: {spec.weights}. "
                "For the canonical model, set AWNPHEN_WEIGHTS or allow the Hugging Face resolver to download it."
            )
        if self.model is not None and self.model_id == spec.id and self.loaded_weights == spec.weights:
            return self.model
        from ultralytics import YOLO
        model = YOLO(str(spec.weights))
        if dict(model.names) != {0: "awn", 1: "spikelet"}:
            raise ValueError(f"Model class mapping mismatch: {model.names}")
        self.model = model
        self.model_id = spec.id
        self.loaded_weights = spec.weights
        return model

    def preload(self, model_id=None):
        spec = model_spec(model_id)
        self._load_model(spec)
        return spec

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
    "MODEL_REGISTRY", "ModelSpec", "ROOT", "SUPPORTED_ADAPTERS", "WEIGHTS",
    "model_catalog", "model_spec", "register_custom_model", "remove_custom_model",
    "refresh_model_registry",
]
