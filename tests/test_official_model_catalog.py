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


def test_official_model_catalog_has_curated_six(monkeypatch, tmp_path):
    backend = _backend(monkeypatch, tmp_path)
    models = backend.model_catalog()
    official = [item for item in models if item["official"]]
    assert [item["id"] for item in official] == [
        "yolo11n-canonical",
        "yolo11m-official",
        "yolo11x-official",
        "maskrcnn-r50-fpn-v2",
        "rfdetr-seg-xl",
        "mask2former-swin-l",
    ]
    assert official[0]["default"] is True
    assert official[0]["positioning"] == "Default / fastest"
    assert official[-1]["positioning"] == "Highest-quality structural model"
    assert official[-1]["page_seconds"] > official[0]["page_seconds"]


def test_optional_models_are_downloadable_not_preinstalled(monkeypatch, tmp_path):
    backend = _backend(monkeypatch, tmp_path)
    models = {item["id"]: item for item in backend.model_catalog()}
    for model_id in (
        "yolo11m-official",
        "yolo11x-official",
        "maskrcnn-r50-fpn-v2",
        "rfdetr-seg-xl",
        "mask2former-swin-l",
    ):
        assert models[model_id]["downloadable"] is True
        assert models[model_id]["installed"] is False
