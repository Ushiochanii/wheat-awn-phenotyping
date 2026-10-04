"""Awn Studio model library plus optional user-added local checkpoints."""
from __future__ import annotations

from dataclasses import dataclass
from importlib.util import find_spec
from pathlib import Path
import hashlib
import json
import os
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

DEFAULT_MODEL_ID = "yolo11n-canonical"
OFFICIAL_MODEL_REPO = "anpanchanii/awn-studio-model-zoo"
OFFICIAL_MODELS_DIR = Path(
    os.environ.get(
        "AWN_STUDIO_OFFICIAL_MODELS",
        Path.home() / ".cache" / "awn-studio" / "models",
    )
).expanduser()
CUSTOM_MODELS_PATH = Path(
    os.environ.get(
        "AWN_STUDIO_CUSTOM_MODELS",
        Path.home() / ".config" / "awn-studio" / "models.json",
    )
).expanduser()

SUPPORTED_ADAPTERS = {
    "ultralytics_yolo_seg": "Ultralytics YOLO segmentation",
    "torchvision_maskrcnn": "Torchvision Mask R-CNN",
    "mask2former_segmentation": "Mask2Former segmentation",
    "rfdetr_segmentation": "RF-DETR segmentation",
}

_RUNTIME_REQUIREMENTS = {
    "ultralytics_yolo_seg": ("ultralytics", None),
    "torchvision_maskrcnn": ("torchvision", None),
    "mask2former_segmentation": (
        "transformers",
        'Install the optional runtime with: python -m pip install -e ".[mask2former]"',
    ),
    "rfdetr_segmentation": (
        "rfdetr",
        'Install the optional runtime with: python -m pip install -e ".[rfdetr]"',
    ),
}


@dataclass(frozen=True)
class ModelSpec:
    id: str
    name: str
    weights: Path
    adapter: str = "ultralytics_yolo_seg"
    description: str = ""
    custom: bool = False
    official: bool = False
    remote_path: str | None = None
    sha256: str | None = None
    companion_files: tuple[str, ...] = ()
    size_bytes: int | None = None
    positioning: str = ""
    quality_note: str = ""
    page_seconds: float | None = None

    @property
    def installed(self) -> bool:
        if not self.weights.is_file():
            return False
        return all(
            (OFFICIAL_MODELS_DIR / path).is_file()
            for path in self.companion_files
        )

    @property
    def runtime_ready(self) -> bool:
        module, _ = _RUNTIME_REQUIREMENTS.get(self.adapter, (None, None))
        return module is None or find_spec(module) is not None

    @property
    def runtime_hint(self) -> str | None:
        if self.runtime_ready:
            return None
        _, hint = _RUNTIME_REQUIREMENTS.get(self.adapter, (None, None))
        return hint or f"Missing runtime for {self.adapter}."

    @property
    def available(self) -> bool:
        return self.installed and self.runtime_ready

    def public(self, *, default: bool = False) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "adapter": self.adapter,
            "description": self.description,
            "available": self.available,
            "installed": self.installed,
            "runtime_ready": self.runtime_ready,
            "runtime_hint": self.runtime_hint,
            "default": default,
            "custom": self.custom,
            "official": self.official,
            "downloadable": bool(self.official and self.remote_path),
            "size_bytes": self.size_bytes,
            "positioning": self.positioning,
            "quality_note": self.quality_note,
            "page_seconds": self.page_seconds,
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


def _official_specs() -> tuple[ModelSpec, ...]:
    return (
        ModelSpec(
            id=DEFAULT_MODEL_ID,
            name="YOLO11N · Default",
            weights=_weights_path(),
            description="Fastest and recommended default for routine Awn Studio use.",
            official=True,
            positioning="Default / fastest",
            quality_note="Complete-awn recall 82.7%; strong overall default.",
            page_seconds=2.28600167890545,
            size_bytes=6006116,
        ),
        ModelSpec(
            id="rfdetr-seg-xl",
            name="RF-DETR Seg XL · Transformer",
            weights=OFFICIAL_MODELS_DIR / "rfdetr-seg-xl.pth",
            adapter="rfdetr_segmentation",
            description="Modern transformer segmentation model with low fragmentation.",
            official=True,
            remote_path="rfdetr-seg-xl.pth",
            sha256="f1b79ad06adaca646fd83e62317f38cbec61df9bce0a87a626944322de10dfe8",
            size_bytes=151531795,
            positioning="Modern transformer detector",
            quality_note="Complete-awn recall 81.6%; low fragmentation.",
            page_seconds=12.835252746008337,
        ),
        ModelSpec(
            id="mask2former-swin-l",
            name="Mask2Former Swin-L · Highest quality",
            weights=OFFICIAL_MODELS_DIR / "mask2former-swin-l" / "model.safetensors",
            adapter="mask2former_segmentation",
            description="Highest-quality structural segmentation option in the maintained comparison.",
            official=True,
            remote_path="mask2former-swin-l/model.safetensors",
            companion_files=(
                "mask2former-swin-l/config.json",
                "mask2former-swin-l/preprocessor_config.json",
            ),
            sha256="a69ed458370c01040de51aebf81ac4c475c2db2f2310a03406b142b27fc3148c",
            size_bytes=866104120,
            positioning="Highest-quality structural model",
            quality_note="Complete-awn recall 83.2%; best structural coverage in the maintained comparison.",
            page_seconds=32.96233680099249,
        ),
    )


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
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return []
    return data if isinstance(data, list) else []


def _write_custom_models(items: list[dict]) -> None:
    CUSTOM_MODELS_PATH.parent.mkdir(parents=True, exist_ok=True)
    CUSTOM_MODELS_PATH.write_text(
        json.dumps(items, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _custom_specs() -> tuple[ModelSpec, ...]:
    specs = []
    for item in _read_custom_models():
        try:
            adapter = str(item.get("adapter") or "ultralytics_yolo_seg")
            if adapter not in SUPPORTED_ADAPTERS:
                continue
            specs.append(
                ModelSpec(
                    id=str(item["id"]),
                    name=str(item["name"]),
                    weights=_normalize_model_path(item["weights"]),
                    adapter=adapter,
                    description=str(item.get("description") or "User-added local model."),
                    custom=True,
                )
            )
        except Exception:
            continue
    return tuple(specs)


MODEL_REGISTRY: dict[str, ModelSpec] = {}


def refresh_model_registry() -> dict[str, ModelSpec]:
    registry = {spec.id: spec for spec in _official_specs()}
    for spec in _custom_specs():
        if spec.id not in registry:
            registry[spec.id] = spec
    MODEL_REGISTRY.clear()
    MODEL_REGISTRY.update(registry)
    return MODEL_REGISTRY


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


def _verify_sha256(path: Path, expected: str | None) -> None:
    if not expected:
        return
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != expected:
        try:
            path.unlink()
        except OSError:
            pass
        raise RuntimeError(
            f"Checksum verification failed for {path.name}: expected {expected}, got {actual}"
        )


def install_official_model(model_id: str) -> ModelSpec:
    spec = model_spec(model_id)
    if not spec.official:
        raise ValueError("Only models from the Awn Studio Model Zoo can be downloaded here.")
    if spec.id == DEFAULT_MODEL_ID:
        from awnphen.model import resolve_weights
        path = resolve_weights()
        _verify_sha256(path, "a7a5cf23bf5d35266e4fa6b1dc0244ee802026a381548bcd202f04b3ebf42097")
        refresh_model_registry()
        return model_spec(model_id)
    if not spec.remote_path:
        raise ValueError(f"No download is configured for {spec.name}.")

    from huggingface_hub import hf_hub_download

    OFFICIAL_MODELS_DIR.mkdir(parents=True, exist_ok=True)
    primary = Path(
        hf_hub_download(
            repo_id=OFFICIAL_MODEL_REPO,
            filename=spec.remote_path,
            local_dir=OFFICIAL_MODELS_DIR,
        )
    )
    _verify_sha256(primary, spec.sha256)
    for filename in spec.companion_files:
        hf_hub_download(
            repo_id=OFFICIAL_MODEL_REPO,
            filename=filename,
            local_dir=OFFICIAL_MODELS_DIR,
        )
    refresh_model_registry()
    return model_spec(model_id)


def register_custom_model(
    *,
    name: str,
    weights: str,
    adapter: str = "ultralytics_yolo_seg",
    description: str = "",
) -> ModelSpec:
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
    items.append(
        {
            "id": model_id,
            "name": name,
            "weights": str(path),
            "adapter": adapter,
            "description": str(description or ""),
        }
    )
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


refresh_model_registry()
DEFAULT_MODEL = MODEL_REGISTRY[DEFAULT_MODEL_ID]
MODEL_NAME = DEFAULT_MODEL.name
WEIGHTS = DEFAULT_MODEL.weights


def resolve_compute_device(device="auto") -> str:
    value = str(device or "auto").strip().lower()
    if value not in {"", "auto"}:
        return str(device)
    try:
        import torch
        if torch.cuda.is_available():
            return "0"
        mps = getattr(torch.backends, "mps", None)
        if mps is not None and mps.is_available():
            return "mps"
    except Exception:
        pass
    return "cpu"


class Engine:
    """Lazy single-active-model cache used by Awn Studio."""

    def __init__(self, device="auto", *, physical_closeout_runner=None, reconciliation_runner=None):
        self.device = resolve_compute_device(device)
        self.physical_closeout_runner = physical_closeout_runner
        self.reconciliation_runner = reconciliation_runner
        self.model = None
        self.model_id = None
        self.loaded_weights = None

    def _torch_device(self) -> str:
        value = str(self.device or "cpu")
        if value == "cpu":
            return "cpu"
        if value.isdigit():
            return f"cuda:{value}"
        return value

    def _release_model(self) -> None:
        model = self.model
        self.model = None
        self.model_id = None
        self.loaded_weights = None
        close = getattr(model, "close", None)
        if callable(close):
            close()
        try:
            import gc
            import torch
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass

    def _load_ultralytics(self, spec: ModelSpec):
        from ultralytics import YOLO
        model = YOLO(str(spec.weights))
        if dict(model.names) != {0: "awn", 1: "spikelet"}:
            raise ValueError(f"Model class mapping mismatch: {model.names}")
        return model

    def _load_maskrcnn(self, spec: ModelSpec):
        import torch
        from torchvision.models.detection import maskrcnn_resnet50_fpn_v2
        from torchvision.models.detection.faster_rcnn import FastRCNNPredictor
        from torchvision.models.detection.mask_rcnn import MaskRCNNPredictor
        from awnphen.modeling.inference.torchvision_maskrcnn import TorchvisionMaskRCNNAdapter

        payload = torch.load(spec.weights, map_location="cpu", weights_only=True)
        config = dict(payload.get("config") or {})
        model_cfg = dict(config.get("model") or {})
        proposal = dict(model_cfg.get("proposal_budget") or {})
        num_classes = int(model_cfg.get("num_classes_with_background", 3))
        model = maskrcnn_resnet50_fpn_v2(
            weights=None,
            weights_backbone=None,
            min_size=int(model_cfg.get("min_size", 640)),
            max_size=int(model_cfg.get("max_size", 640)),
            rpn_pre_nms_top_n_train=int(proposal.get("rpn_pre_nms_top_n_train", 2000)),
            rpn_post_nms_top_n_train=int(proposal.get("rpn_post_nms_top_n_train", 2000)),
            rpn_pre_nms_top_n_test=int(proposal.get("rpn_pre_nms_top_n_test", 1000)),
            rpn_post_nms_top_n_test=int(proposal.get("rpn_post_nms_top_n_test", 1000)),
            box_batch_size_per_image=int(proposal.get("box_batch_size_per_image", 512)),
            box_detections_per_img=int(proposal.get("detections_per_img", 100)),
        )
        box_features = model.roi_heads.box_predictor.cls_score.in_features
        model.roi_heads.box_predictor = FastRCNNPredictor(box_features, num_classes)
        mask_features = model.roi_heads.mask_predictor.conv5_mask.in_channels
        model.roi_heads.mask_predictor = MaskRCNNPredictor(mask_features, 256, num_classes)
        model.load_state_dict(payload["model"], strict=True)
        return TorchvisionMaskRCNNAdapter(
            model=model,
            device=torch.device(self._torch_device()),
            input_size=640,
            mask_threshold=0.5,
            checkpoint_path=spec.weights,
        )

    def _load_mask2former(self, spec: ModelSpec):
        import torch
        from transformers import AutoImageProcessor, Mask2FormerForUniversalSegmentation
        from awnphen.modeling.inference.mask2former_segmentation import Mask2FormerSegmentationAdapter

        checkpoint_dir = spec.weights.parent
        processor = AutoImageProcessor.from_pretrained(checkpoint_dir, local_files_only=True)
        model = Mask2FormerForUniversalSegmentation.from_pretrained(
            checkpoint_dir,
            local_files_only=True,
        )
        model.to(torch.device(self._torch_device())).eval()
        return Mask2FormerSegmentationAdapter(
            model=model,
            processor=processor,
            checkpoint_dir=checkpoint_dir,
            input_size=640,
        )

    def _load_rfdetr(self, spec: ModelSpec):
        from rfdetr import RFDETRSegXLarge
        from awnphen.modeling.inference.rfdetr_segmentation import RFDETRSegmentationAdapter

        device = self._torch_device()
        if device.startswith("cuda:"):
            device = "cuda"
        wrapper = RFDETRSegXLarge.from_checkpoint(
            spec.weights,
            device=device,
            trust_checkpoint=True,
        )
        return RFDETRSegmentationAdapter(
            model=wrapper,
            input_size=624,
            checkpoint_path=spec.weights,
        )

    def _load_model(self, spec: ModelSpec):
        if not spec.installed:
            raise FileNotFoundError(
                f"{spec.name} is not downloaded yet. Download it from Settings → Measurement."
            )
        if not spec.runtime_ready:
            raise RuntimeError(spec.runtime_hint or f"Runtime for {spec.name} is not installed.")
        if (
            self.model is not None
            and self.model_id == spec.id
            and self.loaded_weights == spec.weights
        ):
            return self.model
        if self.model is not None:
            self._release_model()

        loaders = {
            "ultralytics_yolo_seg": self._load_ultralytics,
            "torchvision_maskrcnn": self._load_maskrcnn,
            "mask2former_segmentation": self._load_mask2former,
            "rfdetr_segmentation": self._load_rfdetr,
        }
        model = loaders[spec.adapter](spec)
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
    "DEFAULT_MODEL",
    "DEFAULT_MODEL_ID",
    "Engine",
    "MODEL_NAME",
    "MODEL_REGISTRY",
    "ModelSpec",
    "OFFICIAL_MODEL_REPO",
    "ROOT",
    "SUPPORTED_ADAPTERS",
    "WEIGHTS",
    "install_official_model",
    "model_catalog",
    "model_spec",
    "register_custom_model",
    "remove_custom_model",
    "refresh_model_registry",
    "resolve_compute_device",
]
