from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_STUDIO = ROOT / "app" / "awn_studio"
BUNDLED_STUDIO = ROOT / "src" / "awnphen" / "_bundle" / "app" / "awn_studio"
def _files(root: Path) -> dict[Path, bytes]:
    return {
        path.relative_to(root): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    }


def test_awn_studio_bundle_matches_source():
    assert _files(BUNDLED_STUDIO) == _files(SOURCE_STUDIO)
