from pathlib import Path

from awnphen.model import (
    HF_MODEL_REPO,
    HF_MODEL_REVISION,
    HF_MODEL_SHA256,
)

ROOT = Path(__file__).resolve().parents[1]

FORBIDDEN_TEXT = (
    "TODO_CONFIGURE_BEFORE_PUBLICATION",
    "tail42134c",
    "/root/",
    "artifacts/models/controlled_v2_targeted_robust_stage1_640_b20",
    "workbench_inference",
)

TEXT_SUFFIXES = {
    ".py", ".mjs", ".js", ".html", ".css", ".md", ".toml", ".yaml", ".yml",
    ".txt", ".cff",
}


def test_canonical_model_is_pinned():
    assert HF_MODEL_REPO == "anpanchanii/awnphen-yolo11n"
    assert HF_MODEL_REVISION == "7622e142fd3ab720c19f9ed1de085f998eb8c2e6"
    assert HF_MODEL_SHA256 == (
        "a7a5cf23bf5d35266e4fa6b1dc0244ee802026a381548bcd202f04b3ebf42097"
    )


def test_no_model_weights_are_committed():
    forbidden = {".pt", ".pth", ".ckpt", ".onnx"}
    files = [
        path.relative_to(ROOT)
        for path in ROOT.rglob("*")
        if path.is_file() and path.suffix.lower() in forbidden
    ]
    assert files == []


def test_no_private_or_stale_release_paths():
    hits = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        if ".git" in path.parts or path == Path(__file__).resolve():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for needle in FORBIDDEN_TEXT:
            if needle in text:
                hits.append((str(path.relative_to(ROOT)), needle))
    assert hits == []


def test_retired_launcher_is_not_shipped():
    assert not (ROOT / "app" / "awn_studio" / "launch_service.py").exists()
    assert not (
        ROOT
        / "src"
        / "awnphen"
        / "_bundle"
        / "app"
        / "awn_studio"
        / "launch_service.py"
    ).exists()


def test_studio_report_url_matches_generated_report():
    server = (ROOT / "app" / "awn_studio" / "serve_model.py").read_text(
        encoding="utf-8"
    )
    report = (ROOT / "app" / "awn_studio" / "report.py").read_text(
        encoding="utf-8"
    )
    assert "integration_report.html" in server
    assert "integration_report.html" in report
    assert "/image/report.html" not in server
