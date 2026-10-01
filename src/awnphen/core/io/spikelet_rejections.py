"""Load explicit human-reviewed physical spikelet rejection records."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


def load_spikelet_rejection_manifest(
    path: str | Path,
) -> dict[str, dict[str, Mapping[str, Any]]]:
    """Return page -> detection_id -> audited rejection metadata."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    pages = payload.get("pages", {})
    result: dict[str, dict[str, Mapping[str, Any]]] = {}

    for page_id, records in pages.items():
        page_rows: dict[str, Mapping[str, Any]] = {}
        for record in records:
            detection_id = str(record["detection_id"])
            if record.get("decision") != "reject":
                raise ValueError(
                    "Spikelet rejection manifest currently accepts only decision='reject'"
                )
            if detection_id in page_rows:
                raise ValueError(
                    f"Duplicate rejected spikelet detection_id for {page_id}: {detection_id}"
                )
            page_rows[detection_id] = dict(record)
        result[str(page_id)] = page_rows

    return result


def rejected_spikelet_detection_ids(
    manifest: Mapping[str, Mapping[str, Mapping[str, Any]]],
    page_id: str,
) -> frozenset[str]:
    return frozenset(
        str(value)
        for value in manifest.get(str(page_id), {})
    )


__all__ = [
    "load_spikelet_rejection_manifest",
    "rejected_spikelet_detection_ids",
]
