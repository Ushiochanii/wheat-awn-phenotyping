"""Deterministic IDs for inference snapshots and physical entities.

设计原则：
1. detection ID 绑定具体 analysis snapshot + page + source record；
2. physical entity ID 由 source detection IDs 派生，不使用 cleaned array index；
3. 多 fragment physical awn 的 source 顺序不影响 ID；
4. 不承诺跨不同 snapshot 自动保持同一个 physical ID。
   跨 snapshot 的 UI override 迁移必须通过后续 reconciliation/matching 完成。
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from typing import NewType

SnapshotId = NewType("SnapshotId", str)
DetectionId = NewType("DetectionId", str)
PhysicalEntityId = NewType("PhysicalEntityId", str)

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slug(value: str) -> str:
    text = _SLUG_RE.sub("-", str(value).strip().lower()).strip("-")
    if not text:
        raise ValueError("ID token must contain at least one alphanumeric character")
    return text


def _digest(namespace: str, payload) -> str:
    canonical = json.dumps(
        {
            "namespace": namespace,
            "payload": payload,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.blake2b(
        canonical,
        digest_size=10,
        person=b"wheat-awn-id",
    ).hexdigest()


def make_snapshot_id(provenance: Mapping[str, object]) -> SnapshotId:
    """Create a deterministic analysis-snapshot ID from immutable provenance.

    Typical provenance keys include model SHA, inference artifact SHA, code/tag, and
    behavior/config fingerprint. Mapping key order does not affect the result.
    """
    if not provenance:
        raise ValueError("snapshot provenance must not be empty")

    normalized = {
        str(key): value
        for key, value in provenance.items()
    }
    return SnapshotId(
        f"snap_{_digest('snapshot', normalized)}"
    )


def make_detection_id(
    *,
    snapshot_id: str,
    page_id: str,
    class_name: str,
    source_record_index: int,
) -> DetectionId:
    """Identify one immutable detection inside a specific inference snapshot."""
    if int(source_record_index) < 0:
        raise ValueError("source_record_index must be >= 0")

    class_slug = _slug(class_name)
    page_slug = _slug(page_id)
    payload = {
        "snapshot_id": str(snapshot_id),
        "page_id": str(page_id),
        "class_name": str(class_name),
        "source_record_index": int(source_record_index),
    }
    digest = _digest("detection", payload)
    return DetectionId(
        f"det_{class_slug}_{page_slug}_{digest}"
    )


def make_recovery_detection_id(
    *,
    snapshot_id: str,
    page_id: str,
    stage: str,
    tile_index: int,
    detection_index: int,
    component_id: int,
) -> DetectionId:
    """Identify one component from a recovery-only local inference pass."""
    for name, value in (
        ("tile_index", tile_index),
        ("detection_index", detection_index),
        ("component_id", component_id),
    ):
        if int(value) < 0:
            raise ValueError(f"{name} must be >= 0")

    page_slug = _slug(page_id)
    stage_slug = _slug(stage)
    payload = {
        "snapshot_id": str(snapshot_id),
        "page_id": str(page_id),
        "stage": str(stage),
        "tile_index": int(tile_index),
        "detection_index": int(detection_index),
        "component_id": int(component_id),
    }
    digest = _digest("recovery_detection", payload)
    return DetectionId(
        f"det_recovery_{stage_slug}_{page_slug}_{digest}"
    )


def _make_physical_entity_id(
    *,
    entity_kind: str,
    snapshot_id: str,
    page_id: str,
    source_detection_ids: Sequence[str],
) -> PhysicalEntityId:
    sources = sorted(
        {
            str(source_id)
            for source_id in source_detection_ids
        }
    )
    if not sources:
        raise ValueError(
            "physical entity must have at least one source detection ID"
        )

    kind_slug = _slug(entity_kind)
    page_slug = _slug(page_id)
    payload = {
        "snapshot_id": str(snapshot_id),
        "page_id": str(page_id),
        "entity_kind": str(entity_kind),
        "source_detection_ids": sources,
    }
    digest = _digest(
        f"physical:{entity_kind}",
        payload,
    )
    return PhysicalEntityId(
        f"{kind_slug}_{page_slug}_{digest}"
    )


def make_physical_spikelet_id(
    *,
    snapshot_id: str,
    page_id: str,
    source_detection_ids: Sequence[str],
) -> PhysicalEntityId:
    """Create a physical-spikelet ID stable to cleanup/reordering within a snapshot."""
    return _make_physical_entity_id(
        entity_kind="spk",
        snapshot_id=snapshot_id,
        page_id=page_id,
        source_detection_ids=source_detection_ids,
    )


def make_physical_awn_id(
    *,
    snapshot_id: str,
    page_id: str,
    source_detection_ids: Sequence[str],
) -> PhysicalEntityId:
    """Create a physical-awn ID; fragment source order does not affect the result."""
    return _make_physical_entity_id(
        entity_kind="awn",
        snapshot_id=snapshot_id,
        page_id=page_id,
        source_detection_ids=source_detection_ids,
    )
