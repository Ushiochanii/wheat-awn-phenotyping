"""Load explicit human-reviewed spikelet attachment overrides."""
from __future__ import annotations

import json
from pathlib import Path


def load_forced_spikelet_attachments(
    path: Path,
    page: str,
) -> tuple[tuple[str, str], ...]:
    """Return exact small->large hypothesis pairs for one page.

    Missing files/pages intentionally mean no override. The IDs are exact so a
    reviewed correction cannot silently spill onto another hypothesis.
    """
    path = Path(path)
    if not path.is_file():
        return ()
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("pages", {}).get(str(page), [])
    return tuple(
        (
            str(row["small_hypothesis_id"]),
            str(row["large_hypothesis_id"]),
        )
        for row in rows
    )


__all__ = ["load_forced_spikelet_attachments"]
