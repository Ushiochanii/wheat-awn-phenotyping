from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_STUDIO = ROOT / "app" / "awn_studio"
BUNDLED_STUDIO = ROOT / "src" / "awnphen" / "_bundle" / "app" / "awn_studio"
SOURCE_DEMO = ROOT / "examples" / "demo_page.jpg"
BUNDLED_DEMO = ROOT / "src" / "awnphen" / "_bundle" / "examples" / "demo_page.jpg"


def _files(root: Path) -> dict[Path, bytes]:
    return {
        path.relative_to(root): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    }


def test_awn_studio_bundle_matches_source():
    assert _files(BUNDLED_STUDIO) == _files(SOURCE_STUDIO)


def test_demo_bundle_matches_source():
    assert BUNDLED_DEMO.read_bytes() == SOURCE_DEMO.read_bytes()
