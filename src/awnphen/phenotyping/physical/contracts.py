"""Physical Reconstruction foundations for awnphen_next."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from awnphen.core.domain.physical import (
    HypothesisStatus,
    InstanceHypothesis,
    PhysicalAwn,
    PhysicalSpikelet,
)
from awnphen.core.domain.physical_provenance import (
    HypothesisId,
    OperationProvenance,
    SnapshotId,
    make_physical_awn_id,
    make_physical_spikelet_id,
)

PHYSICAL_SEED_IMPLEMENTATION = "phase4a_physical_seed_v1"


def _sorted_unique_text(values) -> tuple[str, ...]:
    normalized = tuple(str(value) for value in values)
    if len(normalized) != len(set(normalized)):
        raise ValueError("physical seed IDs must be unique")
    return tuple(sorted(normalized))


@dataclass(frozen=True, slots=True)
class PhysicalSeedResult:
    """One page of physical-entity seeds plus unresolved hypotheses."""

    page_id: str
    snapshot_id: SnapshotId
    source_hypothesis_ids: tuple[HypothesisId, ...]
    physical_awns: tuple[PhysicalAwn, ...]
    physical_spikelets: tuple[PhysicalSpikelet, ...]
    unresolved_hypothesis_ids: tuple[HypothesisId, ...]

    def __post_init__(self) -> None:
        page_id = str(self.page_id).strip()
        if not page_id:
            raise ValueError("page_id must not be empty")

        sources = _sorted_unique_text(self.source_hypothesis_ids)
        unresolved = _sorted_unique_text(self.unresolved_hypothesis_ids)
        seeded_ids = [
            str(item.seed_hypothesis_id)
            for item in (*self.physical_awns, *self.physical_spikelets)
        ]
        if len(seeded_ids) != len(set(seeded_ids)):
            raise ValueError("one hypothesis cannot seed multiple physical entities")

        source_set = set(sources)
        seeded_set = set(seeded_ids)
        unresolved_set = set(unresolved)
        if seeded_set & unresolved_set:
            raise ValueError("seeded and unresolved hypotheses must be disjoint")
        if seeded_set | unresolved_set != source_set:
            raise ValueError(
                "physical seed result must partition source hypotheses"
            )

        for entity in (*self.physical_awns, *self.physical_spikelets):
            if entity.page_id != page_id:
                raise ValueError("physical seed entity page mismatch")
            if str(entity.snapshot_id) != str(self.snapshot_id):
                raise ValueError("physical seed entity snapshot mismatch")

        object.__setattr__(self, "page_id", page_id)
        object.__setattr__(
            self,
            "source_hypothesis_ids",
            tuple(HypothesisId(value) for value in sources),
        )
        object.__setattr__(
            self,
            "unresolved_hypothesis_ids",
            tuple(HypothesisId(value) for value in unresolved),
        )
        object.__setattr__(
            self,
            "physical_awns",
            tuple(sorted(
                self.physical_awns,
                key=lambda item: str(item.physical_awn_id),
            )),
        )
        object.__setattr__(
            self,
            "physical_spikelets",
            tuple(sorted(
                self.physical_spikelets,
                key=lambda item: str(item.physical_spikelet_id),
            )),
        )


def _seed_provenance(
    hypothesis: InstanceHypothesis,
    *,
    output_id: str,
) -> OperationProvenance:
    return OperationProvenance(
        operation="seed_physical_entity",
        implementation=PHYSICAL_SEED_IMPLEMENTATION,
        input_ids=(str(hypothesis.hypothesis_id),),
        output_id=output_id,
        status="seeded",
        parameters={
            "source_hypothesis_status": hypothesis.status.value,
            "geometry_strategy": "preserve_reconciliation_geometry",
        },
        evidence={
            "source_evidence_ids": [
                str(value) for value in hypothesis.evidence_ids
            ],
        },
    )


def seed_physical_entities(
    hypotheses: Sequence[InstanceHypothesis],
) -> PhysicalSeedResult:
    """Create one-to-one physical seeds from non-ambiguous hypotheses."""
    ordered = tuple(
        sorted(hypotheses, key=lambda item: str(item.hypothesis_id))
    )
    if not ordered:
        raise ValueError("physical seeding requires at least one hypothesis")

    page_ids = {item.page_id for item in ordered}
    snapshots = {str(item.snapshot_id) for item in ordered}
    if len(page_ids) != 1:
        raise ValueError("physical seeding requires hypotheses from one page")
    if len(snapshots) != 1:
        raise ValueError(
            "physical seeding requires hypotheses from one snapshot"
        )

    page_id = ordered[0].page_id
    snapshot_id = ordered[0].snapshot_id
    awns: list[PhysicalAwn] = []
    spikelets: list[PhysicalSpikelet] = []
    unresolved: list[HypothesisId] = []

    for hypothesis in ordered:
        if hypothesis.status is HypothesisStatus.AMBIGUOUS:
            unresolved.append(hypothesis.hypothesis_id)
            continue

        if hypothesis.class_name == "awn":
            output_id = make_physical_awn_id(
                snapshot_id=str(snapshot_id),
                page_id=page_id,
                seed_hypothesis_id=str(hypothesis.hypothesis_id),
            )
            awns.append(
                PhysicalAwn.create(
                    snapshot_id=snapshot_id,
                    page_id=page_id,
                    seed_hypothesis_id=hypothesis.hypothesis_id,
                    source_hypothesis_ids=(hypothesis.hypothesis_id,),
                    source_evidence_ids=hypothesis.evidence_ids,
                    geometry=hypothesis.geometry,
                    provenance=(
                        _seed_provenance(
                            hypothesis,
                            output_id=str(output_id),
                        ),
                    ),
                )
            )
            continue

        if hypothesis.class_name == "spikelet":
            output_id = make_physical_spikelet_id(
                snapshot_id=str(snapshot_id),
                page_id=page_id,
                seed_hypothesis_id=str(hypothesis.hypothesis_id),
            )
            spikelets.append(
                PhysicalSpikelet.create(
                    snapshot_id=snapshot_id,
                    page_id=page_id,
                    seed_hypothesis_id=hypothesis.hypothesis_id,
                    source_hypothesis_ids=(hypothesis.hypothesis_id,),
                    source_evidence_ids=hypothesis.evidence_ids,
                    geometry=hypothesis.geometry,
                    provenance=(
                        _seed_provenance(
                            hypothesis,
                            output_id=str(output_id),
                        ),
                    ),
                )
            )
            continue

        raise ValueError(
            f"unsupported reconciliation class: {hypothesis.class_name!r}"
        )

    return PhysicalSeedResult(
        page_id=page_id,
        snapshot_id=snapshot_id,
        source_hypothesis_ids=tuple(
            item.hypothesis_id for item in ordered
        ),
        physical_awns=tuple(awns),
        physical_spikelets=tuple(spikelets),
        unresolved_hypothesis_ids=tuple(unresolved),
    )


__all__ = [
    "PHYSICAL_SEED_IMPLEMENTATION",
    "PhysicalSeedResult",
    "seed_physical_entities",
]
