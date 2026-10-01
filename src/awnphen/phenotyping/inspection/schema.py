"""Inspector state contract for the parallel awnphen_next pipeline.

The Inspector is intentionally domain-light. It renders generic visual objects
organized by pipeline stage and layer; scientific meaning remains in stable
object IDs, statuses, metadata, and provenance.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, TypeAlias

from awnphen.core.domain.physical_provenance import OperationProvenance, SnapshotId

SCHEMA_VERSION = "awnphen_inspector_page_state_v1"

Point2D: TypeAlias = tuple[float, float]


class InspectorStage(str, Enum):
    EVIDENCE = "evidence"
    RECONCILIATION = "reconciliation"
    PHYSICAL = "physical"
    REPRESENTATIVE = "representative"
    MEASUREMENT = "measurement"
    SEMANTIC = "semantic"


STAGE_ORDER: tuple[InspectorStage, ...] = (
    InspectorStage.EVIDENCE,
    InspectorStage.RECONCILIATION,
    InspectorStage.PHYSICAL,
    InspectorStage.REPRESENTATIVE,
    InspectorStage.MEASUREMENT,
    InspectorStage.SEMANTIC,
)


class PrimitiveKind(str, Enum):
    POLYGON = "polygon"
    POLYLINE = "polyline"
    POINT = "point"
    CONNECTION = "connection"
    LABEL = "label"


def _require_text(name: str, value: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise ValueError(f"{name} must not be empty")
    return normalized


def _require_finite(name: str, value: float) -> float:
    normalized = float(value)
    if not math.isfinite(normalized):
        raise ValueError(f"{name} must be finite")
    return normalized


def _point(value: Sequence[float]) -> Point2D:
    if len(value) != 2:
        raise ValueError("point must contain exactly two coordinates")
    return (
        _require_finite("point x", value[0]),
        _require_finite("point y", value[1]),
    )


def _points(
    values: Sequence[Sequence[float]],
    *,
    minimum: int,
    name: str,
) -> tuple[Point2D, ...]:
    normalized = tuple(_point(value) for value in values)
    if len(normalized) < minimum:
        raise ValueError(f"{name} requires at least {minimum} points")
    return normalized


def _freeze_jsonlike(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return MappingProxyType(
            {
                str(key): _freeze_jsonlike(item)
                for key, item in value.items()
            }
        )
    if isinstance(value, (tuple, list)):
        return tuple(_freeze_jsonlike(item) for item in value)
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("metadata must not contain NaN or infinity")
        return value
    raise TypeError(
        "metadata must be JSON-compatible; "
        f"unsupported type: {type(value).__name__}"
    )


def _jsonable(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {
            str(key): _jsonable(item)
            for key, item in value.items()
        }
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    if value is None or isinstance(value, (str, int, bool, float)):
        return value
    raise TypeError(
        "value must be JSON-compatible; "
        f"unsupported type: {type(value).__name__}"
    )


@dataclass(frozen=True, slots=True)
class PolygonPrimitive:
    """One polygon with an outer ring and optional hole rings."""

    rings: tuple[tuple[Point2D, ...], ...]
    kind: PrimitiveKind = field(
        default=PrimitiveKind.POLYGON,
        init=False,
    )

    def __post_init__(self) -> None:
        rings = tuple(
            _points(ring, minimum=3, name="polygon ring")
            for ring in self.rings
        )
        if not rings:
            raise ValueError("polygon requires at least one ring")
        object.__setattr__(self, "rings", rings)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "rings": _jsonable(self.rings),
        }


@dataclass(frozen=True, slots=True)
class PolylinePrimitive:
    points: tuple[Point2D, ...]
    kind: PrimitiveKind = field(
        default=PrimitiveKind.POLYLINE,
        init=False,
    )

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "points",
            _points(self.points, minimum=2, name="polyline"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "points": _jsonable(self.points),
        }


@dataclass(frozen=True, slots=True)
class PointPrimitive:
    point: Point2D
    radius_px: float | None = None
    kind: PrimitiveKind = field(
        default=PrimitiveKind.POINT,
        init=False,
    )

    def __post_init__(self) -> None:
        object.__setattr__(self, "point", _point(self.point))
        if self.radius_px is not None:
            radius = _require_finite("radius_px", self.radius_px)
            if radius <= 0:
                raise ValueError("radius_px must be > 0")
            object.__setattr__(self, "radius_px", radius)

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "kind": self.kind.value,
            "point": _jsonable(self.point),
        }
        if self.radius_px is not None:
            payload["radius_px"] = self.radius_px
        return payload


@dataclass(frozen=True, slots=True)
class ConnectionPrimitive:
    """Rendered connection between two domain objects or explicit endpoints."""

    start: Point2D
    end: Point2D
    source_object_id: str | None = None
    target_object_id: str | None = None
    kind: PrimitiveKind = field(
        default=PrimitiveKind.CONNECTION,
        init=False,
    )

    def __post_init__(self) -> None:
        object.__setattr__(self, "start", _point(self.start))
        object.__setattr__(self, "end", _point(self.end))
        if self.source_object_id is not None:
            object.__setattr__(
                self,
                "source_object_id",
                _require_text("source_object_id", self.source_object_id),
            )
        if self.target_object_id is not None:
            object.__setattr__(
                self,
                "target_object_id",
                _require_text("target_object_id", self.target_object_id),
            )

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "kind": self.kind.value,
            "start": _jsonable(self.start),
            "end": _jsonable(self.end),
        }
        if self.source_object_id is not None:
            payload["source_object_id"] = self.source_object_id
        if self.target_object_id is not None:
            payload["target_object_id"] = self.target_object_id
        return payload


@dataclass(frozen=True, slots=True)
class LabelPrimitive:
    anchor: Point2D
    text: str
    kind: PrimitiveKind = field(
        default=PrimitiveKind.LABEL,
        init=False,
    )

    def __post_init__(self) -> None:
        object.__setattr__(self, "anchor", _point(self.anchor))
        object.__setattr__(self, "text", _require_text("label text", self.text))

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "anchor": _jsonable(self.anchor),
            "text": self.text,
        }


VisualPrimitive: TypeAlias = (
    PolygonPrimitive
    | PolylinePrimitive
    | PointPrimitive
    | ConnectionPrimitive
    | LabelPrimitive
)


def primitive_from_dict(payload: Mapping[str, Any]) -> VisualPrimitive:
    kind = PrimitiveKind(str(payload["kind"]))
    if kind is PrimitiveKind.POLYGON:
        return PolygonPrimitive(
            rings=tuple(
                tuple(_point(point) for point in ring)
                for ring in payload["rings"]
            )
        )
    if kind is PrimitiveKind.POLYLINE:
        return PolylinePrimitive(
            points=tuple(_point(point) for point in payload["points"])
        )
    if kind is PrimitiveKind.POINT:
        return PointPrimitive(
            point=_point(payload["point"]),
            radius_px=payload.get("radius_px"),
        )
    if kind is PrimitiveKind.CONNECTION:
        return ConnectionPrimitive(
            start=_point(payload["start"]),
            end=_point(payload["end"]),
            source_object_id=payload.get("source_object_id"),
            target_object_id=payload.get("target_object_id"),
        )
    if kind is PrimitiveKind.LABEL:
        return LabelPrimitive(
            anchor=_point(payload["anchor"]),
            text=str(payload["text"]),
        )
    raise AssertionError(f"unhandled primitive kind: {kind}")


@dataclass(frozen=True, slots=True)
class PageImage:
    image_ref: str
    width_px: int
    height_px: int

    def __post_init__(self) -> None:
        image_ref = _require_text("image_ref", self.image_ref)
        width = int(self.width_px)
        height = int(self.height_px)
        if width <= 0 or height <= 0:
            raise ValueError("image dimensions must be positive")
        object.__setattr__(self, "image_ref", image_ref)
        object.__setattr__(self, "width_px", width)
        object.__setattr__(self, "height_px", height)

    def to_dict(self) -> dict[str, Any]:
        return {
            "image_ref": self.image_ref,
            "width_px": self.width_px,
            "height_px": self.height_px,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "PageImage":
        return cls(
            image_ref=str(payload["image_ref"]),
            width_px=int(payload["width_px"]),
            height_px=int(payload["height_px"]),
        )


@dataclass(frozen=True, slots=True)
class LayerSpec:
    """One toggleable Inspector layer."""

    layer_id: str
    stage: InspectorStage
    title: str
    description: str = ""
    default_visible: bool = True
    default_opacity: float = 1.0
    confidence_filterable: bool = False
    z_index: int = 0
    legend_key: str | None = None

    def __post_init__(self) -> None:
        layer_id = _require_text("layer_id", self.layer_id)
        title = _require_text("layer title", self.title)
        stage = (
            self.stage
            if isinstance(self.stage, InspectorStage)
            else InspectorStage(str(self.stage))
        )
        opacity = _require_finite("default_opacity", self.default_opacity)
        if not 0.0 <= opacity <= 1.0:
            raise ValueError("default_opacity must be within [0, 1]")
        legend = (
            None
            if self.legend_key is None
            else _require_text("legend_key", self.legend_key)
        )

        object.__setattr__(self, "layer_id", layer_id)
        object.__setattr__(self, "stage", stage)
        object.__setattr__(self, "title", title)
        object.__setattr__(self, "description", str(self.description))
        object.__setattr__(self, "default_opacity", opacity)
        object.__setattr__(self, "z_index", int(self.z_index))
        object.__setattr__(self, "legend_key", legend)

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "layer_id": self.layer_id,
            "stage": self.stage.value,
            "title": self.title,
            "description": self.description,
            "default_visible": self.default_visible,
            "default_opacity": self.default_opacity,
            "confidence_filterable": self.confidence_filterable,
            "z_index": self.z_index,
        }
        if self.legend_key is not None:
            payload["legend_key"] = self.legend_key
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "LayerSpec":
        return cls(
            layer_id=str(payload["layer_id"]),
            stage=InspectorStage(str(payload["stage"])),
            title=str(payload["title"]),
            description=str(payload.get("description", "")),
            default_visible=bool(payload.get("default_visible", True)),
            default_opacity=float(payload.get("default_opacity", 1.0)),
            confidence_filterable=bool(
                payload.get("confidence_filterable", False)
            ),
            z_index=int(payload.get("z_index", 0)),
            legend_key=payload.get("legend_key"),
        )


@dataclass(frozen=True, slots=True)
class InspectorObject:
    """One visual view of a stable domain object.

    view_id is unique inside the page state. object_id is the stable domain
    identity and may intentionally appear in multiple layers.
    """

    view_id: str
    object_id: str
    layer_id: str
    stage: InspectorStage
    primitives: tuple[VisualPrimitive, ...]
    label: str | None = None
    status: str | None = None
    confidence: float | None = None
    style_key: str | None = None
    source_object_ids: tuple[str, ...] = ()
    provenance_ids: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        view_id = _require_text("view_id", self.view_id)
        object_id = _require_text("object_id", self.object_id)
        layer_id = _require_text("layer_id", self.layer_id)
        stage = (
            self.stage
            if isinstance(self.stage, InspectorStage)
            else InspectorStage(str(self.stage))
        )
        primitives = tuple(self.primitives)
        if not primitives:
            raise ValueError("InspectorObject requires at least one primitive")
        if not all(
            isinstance(
                primitive,
                (
                    PolygonPrimitive,
                    PolylinePrimitive,
                    PointPrimitive,
                    ConnectionPrimitive,
                    LabelPrimitive,
                ),
            )
            for primitive in primitives
        ):
            raise TypeError("InspectorObject contains an unsupported primitive")

        confidence = self.confidence
        if confidence is not None:
            confidence = _require_finite("confidence", confidence)
            if not 0.0 <= confidence <= 1.0:
                raise ValueError("confidence must be within [0, 1]")

        object.__setattr__(self, "view_id", view_id)
        object.__setattr__(self, "object_id", object_id)
        object.__setattr__(self, "layer_id", layer_id)
        object.__setattr__(self, "stage", stage)
        object.__setattr__(self, "primitives", primitives)
        object.__setattr__(
            self,
            "label",
            None if self.label is None else str(self.label),
        )
        object.__setattr__(
            self,
            "status",
            None if self.status is None else _require_text("status", self.status),
        )
        object.__setattr__(
            self,
            "style_key",
            (
                None
                if self.style_key is None
                else _require_text("style_key", self.style_key)
            ),
        )
        object.__setattr__(self, "confidence", confidence)
        object.__setattr__(
            self,
            "source_object_ids",
            tuple(str(value) for value in self.source_object_ids),
        )
        object.__setattr__(
            self,
            "provenance_ids",
            tuple(str(value) for value in self.provenance_ids),
        )
        object.__setattr__(
            self,
            "tags",
            tuple(str(value) for value in self.tags),
        )
        object.__setattr__(
            self,
            "metadata",
            _freeze_jsonlike(dict(self.metadata)),
        )

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "view_id": self.view_id,
            "object_id": self.object_id,
            "layer_id": self.layer_id,
            "stage": self.stage.value,
            "primitives": [
                primitive.to_dict()
                for primitive in self.primitives
            ],
            "source_object_ids": list(self.source_object_ids),
            "provenance_ids": list(self.provenance_ids),
            "tags": list(self.tags),
            "metadata": _jsonable(self.metadata),
        }
        if self.label is not None:
            payload["label"] = self.label
        if self.status is not None:
            payload["status"] = self.status
        if self.confidence is not None:
            payload["confidence"] = self.confidence
        if self.style_key is not None:
            payload["style_key"] = self.style_key
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "InspectorObject":
        return cls(
            view_id=str(payload["view_id"]),
            object_id=str(payload["object_id"]),
            layer_id=str(payload["layer_id"]),
            stage=InspectorStage(str(payload["stage"])),
            primitives=tuple(
                primitive_from_dict(item)
                for item in payload["primitives"]
            ),
            label=payload.get("label"),
            status=payload.get("status"),
            confidence=payload.get("confidence"),
            style_key=payload.get("style_key"),
            source_object_ids=tuple(payload.get("source_object_ids", ())),
            provenance_ids=tuple(payload.get("provenance_ids", ())),
            tags=tuple(payload.get("tags", ())),
            metadata=dict(payload.get("metadata", {})),
        )


@dataclass(frozen=True, slots=True)
class InspectorPageState:
    """Serializable state consumed by the future Pipeline Inspector UI."""

    page_id: str
    snapshot_id: SnapshotId
    image: PageImage
    layers: tuple[LayerSpec, ...]
    objects: tuple[InspectorObject, ...]
    provenance: tuple[OperationProvenance, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        page_id = _require_text("page_id", self.page_id)
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(
                f"unsupported Inspector schema_version: {self.schema_version}"
            )

        layers = tuple(self.layers)
        objects = tuple(self.objects)
        provenance = tuple(self.provenance)

        layer_ids = [layer.layer_id for layer in layers]
        if len(layer_ids) != len(set(layer_ids)):
            raise ValueError("InspectorPageState layer_id values must be unique")
        layer_by_id = {
            layer.layer_id: layer
            for layer in layers
        }

        view_ids = [item.view_id for item in objects]
        if len(view_ids) != len(set(view_ids)):
            raise ValueError("InspectorPageState view_id values must be unique")

        provenance_ids = [item.provenance_id for item in provenance]
        if len(provenance_ids) != len(set(provenance_ids)):
            raise ValueError(
                "InspectorPageState provenance records must be unique"
            )
        available_provenance = set(provenance_ids)

        for item in objects:
            layer = layer_by_id.get(item.layer_id)
            if layer is None:
                raise ValueError(
                    f"InspectorObject references unknown layer_id: {item.layer_id}"
                )
            if item.stage is not layer.stage:
                raise ValueError(
                    "InspectorObject stage must match its LayerSpec stage"
                )
            missing = set(item.provenance_ids) - available_provenance
            if missing:
                raise ValueError(
                    "InspectorObject references unknown provenance IDs: "
                    + ", ".join(sorted(missing))
                )

        object.__setattr__(self, "page_id", page_id)
        object.__setattr__(self, "layers", layers)
        object.__setattr__(self, "objects", objects)
        object.__setattr__(self, "provenance", provenance)
        object.__setattr__(
            self,
            "metadata",
            _freeze_jsonlike(dict(self.metadata)),
        )

    @property
    def domain_object_ids(self) -> tuple[str, ...]:
        return tuple(
            sorted({item.object_id for item in self.objects})
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "page_id": self.page_id,
            "snapshot_id": str(self.snapshot_id),
            "image": self.image.to_dict(),
            "stage_order": [stage.value for stage in STAGE_ORDER],
            "layers": [layer.to_dict() for layer in self.layers],
            "objects": [item.to_dict() for item in self.objects],
            "provenance": [item.to_dict() for item in self.provenance],
            "metadata": _jsonable(self.metadata),
        }

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            indent=indent,
            allow_nan=False,
        )

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "InspectorPageState":
        provenance: list[OperationProvenance] = []
        for item in payload.get("provenance", ()):
            record = OperationProvenance(
                operation=str(item["operation"]),
                implementation=str(item["implementation"]),
                input_ids=tuple(item.get("input_ids", ())),
                output_id=item.get("output_id"),
                status=str(item["status"]),
                parameters=dict(item.get("parameters", {})),
                evidence=dict(item.get("evidence", {})),
            )
            expected_id = item.get("provenance_id")
            if (
                expected_id is not None
                and str(expected_id) != record.provenance_id
            ):
                raise ValueError(
                    "serialized provenance_id does not match provenance content"
                )
            provenance.append(record)

        return cls(
            schema_version=str(payload["schema_version"]),
            page_id=str(payload["page_id"]),
            snapshot_id=SnapshotId(str(payload["snapshot_id"])),
            image=PageImage.from_dict(payload["image"]),
            layers=tuple(
                LayerSpec.from_dict(item)
                for item in payload.get("layers", ())
            ),
            objects=tuple(
                InspectorObject.from_dict(item)
                for item in payload.get("objects", ())
            ),
            provenance=tuple(provenance),
            metadata=dict(payload.get("metadata", {})),
        )

    @classmethod
    def from_json(cls, payload: str) -> "InspectorPageState":
        decoded = json.loads(payload)
        if not isinstance(decoded, dict):
            raise ValueError("Inspector page-state JSON root must be an object")
        return cls.from_dict(decoded)
