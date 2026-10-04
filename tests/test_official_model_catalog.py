from __future__ import annotations

import importlib
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STUDIO = ROOT / "app" / "awn_studio"


def _backend(monkeypatch, tmp_path):
    monkeypatch.setenv("AWN_STUDIO_OFFICIAL_MODELS", str(tmp_path / "models"))
    sys.path.insert(0, str(STUDIO))
    try:
        sys.modules.pop("inference_backend", None)
        return importlib.import_module("inference_backend")
    finally:
        sys.path.remove(str(STUDIO))


def test_model_library_has_curated_three(monkeypatch, tmp_path):
    backend = _backend(monkeypatch, tmp_path)
    models = backend.model_catalog()
    curated = [item for item in models if item["official"]]
    assert [item["id"] for item in curated] == [
        "yolo11n-canonical",
        "rfdetr-seg-xl",
        "mask2former-swin-l",
    ]
    assert curated[0]["default"] is True
    assert curated[0]["positioning"] == "Default / fastest"
    assert curated[-1]["positioning"] == "Highest-quality structural model"
    assert curated[-1]["page_seconds"] > curated[0]["page_seconds"]


def test_optional_models_are_downloadable_not_preinstalled(monkeypatch, tmp_path):
    backend = _backend(monkeypatch, tmp_path)
    models = {item["id"]: item for item in backend.model_catalog()}
    for model_id in ("rfdetr-seg-xl", "mask2former-swin-l"):
        assert models[model_id]["downloadable"] is True
        assert models[model_id]["installed"] is False
