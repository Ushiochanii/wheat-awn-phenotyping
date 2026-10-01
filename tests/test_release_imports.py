from awnphen.cli import build_parser
from awnphen.model import HF_MODEL_REPO


def test_cli_commands_exist():
    help_text = build_parser().format_help()
    assert "predict" in help_text
    assert "demo" in help_text
    assert "studio" in help_text


def test_hf_repo_is_configured():
    assert HF_MODEL_REPO == "anpanchanii/awnphen-yolo11n"
