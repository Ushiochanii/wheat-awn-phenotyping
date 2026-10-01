"""Lightweight job-state serialization for the local Awn Studio model service."""
from __future__ import annotations

import json
from pathlib import Path

_INTERNAL_KEYS = {"preview", "result", "result_file"}


def public_job_payload(job: dict) -> dict:
    """Build the API payload, materializing a completed result only on demand."""
    payload = {
        key: value
        for key, value in job.items()
        if key not in _INTERNAL_KEYS
    }
    if job.get("status") == "done" and job.get("result_file"):
        result_path = Path(job["result_file"])
        result = json.loads(result_path.read_text(encoding="utf-8"))
        if job.get("report"):
            result["report"] = job["report"]
        payload["result"] = result
    return payload


def persistent_job_payload(job: dict) -> dict:
    """Build the compact on-disk job metadata without duplicating result data."""
    payload = {
        key: value
        for key, value in job.items()
        if key not in _INTERNAL_KEYS
    }
    if job.get("result_file"):
        payload["result_file"] = Path(job["result_file"]).name
    return payload


__all__ = ["persistent_job_payload", "public_job_payload"]
