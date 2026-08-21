"""Governed re-synthesis boundary for AgentOS Cognitive Kernel.

AgentOS prepares a bounded association packet and validates the returned insight.
The creative synthesizer itself is pluggable (LLM, web agent, A2A agent, human,
etc.). Novel prose is never trusted merely because a model produced it.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable, Mapping, Sequence

from agent_core.cognitive_index import AssociationSet
from runtime_core.cognitive_ir import (
    EvidenceRef,
    KnowledgeCandidate,
    SynthesisRecord,
    merge_evidence,
)


@dataclass(frozen=True)
class SynthesisSource:
    knowledge_id: str
    project_id: str
    kind: str
    statement: str
    abstraction_level: str
    confidence: float
    evidence: tuple[EvidenceRef, ...]

    @classmethod
    def from_candidate(cls, candidate: KnowledgeCandidate) -> "SynthesisSource":
        return cls(
            knowledge_id=candidate.knowledge_id,
            project_id=candidate.project_id,
            kind=candidate.kind,
            statement=candidate.statement,
            abstraction_level=candidate.abstraction_level,
            confidence=float(candidate.confidence),
            evidence=candidate.evidence,
        )


@dataclass(frozen=True)
class SynthesisEnvelope:
    """Disposable bounded context for one synthesis attempt."""

    project_id: str
    trigger_ref: str
    trigger_text: str
    synthesis_kind: str
    near_sources: tuple[SynthesisSource, ...]
    far_sources: tuple[SynthesisSource, ...]
    required_rules: tuple[str, ...] = (
        "output_is_candidate_not_fact",
        "retain_supporting_and_contradicting_evidence",
        "cite_source_knowledge_ids",
        "state_uncertainty_explicitly",
        "do_not_trigger_external_actions",
    )

    @property
    def source_ids(self) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys(
                [
                    *(item.knowledge_id for item in self.near_sources),
                    *(item.knowledge_id for item in self.far_sources),
                ]
            )
        )


class CognitiveSynthesisBoundary:
    """Prepares and normalizes re-synthesis without owning a model runtime."""

    def __init__(self, lookup: Callable[[str], KnowledgeCandidate | None]) -> None:
        self.lookup = lookup

    def build_envelope(
        self,
        associations: AssociationSet,
        *,
        trigger_text: str,
        project_id: str,
        synthesis_kind: str = "incremental",
    ) -> SynthesisEnvelope:
        if synthesis_kind not in {"incremental", "global", "cross_project", "brainstorm"}:
            raise ValueError("invalid synthesis_kind")
        if not str(trigger_text or "").strip():
            raise ValueError("trigger_text is required")

        def resolve(ids: Sequence[str]) -> tuple[SynthesisSource, ...]:
            values: list[SynthesisSource] = []
            for knowledge_id in ids:
                candidate = self.lookup(knowledge_id)
                if candidate is None:
                    raise LookupError(f"missing synthesis source: {knowledge_id}")
                values.append(SynthesisSource.from_candidate(candidate))
            return tuple(values)

        near = resolve([item.knowledge_id for item in associations.near])
        far = resolve([item.knowledge_id for item in associations.far])
        return SynthesisEnvelope(
            project_id=project_id,
            trigger_ref=associations.trigger_ref,
            trigger_text=trigger_text,
            synthesis_kind=synthesis_kind,
            near_sources=near,
            far_sources=far,
        )

    def normalize_candidate(
        self,
        envelope: SynthesisEnvelope,
        proposed: KnowledgeCandidate,
        *,
        trigger_evidence: Sequence[EvidenceRef] = (),
    ) -> KnowledgeCandidate:
        """Force a synthesizer result back behind AgentOS trust boundaries."""
        source_candidates = [self.lookup(item) for item in envelope.source_ids]
        if any(item is None for item in source_candidates):
            raise LookupError("one or more synthesis sources disappeared")
        source_candidates = [item for item in source_candidates if item is not None]

        inherited_evidence = merge_evidence(
            *(item.evidence for item in source_candidates),
            trigger_evidence,
            proposed.evidence,
        )
        derived_from = tuple(
            dict.fromkeys([*envelope.source_ids, *proposed.derived_from])
        )
        metadata = dict(proposed.metadata)
        metadata.update(
            {
                "synthesis_trigger_ref": envelope.trigger_ref,
                "synthesis_kind": envelope.synthesis_kind,
                "near_source_ids": [item.knowledge_id for item in envelope.near_sources],
                "far_source_ids": [item.knowledge_id for item in envelope.far_sources],
                "governance_state": "candidate",
            }
        )

        # A synthesizer cannot self-promote its output, regardless of the status or
        # abstraction level it attempted to return.
        return replace(
            proposed,
            project_id=envelope.project_id,
            status="candidate",
            abstraction_level="working",
            evidence=inherited_evidence,
            derived_from=derived_from,
            metadata=metadata,
        )

    def record(
        self,
        envelope: SynthesisEnvelope,
        candidates: Sequence[KnowledgeCandidate],
    ) -> SynthesisRecord:
        normalized_ids = set(envelope.source_ids)
        for candidate in candidates:
            if candidate.status != "candidate":
                raise ValueError("synthesis record only accepts governed candidates")
            if not normalized_ids.issubset(set(candidate.derived_from)):
                raise ValueError("candidate is missing synthesis source provenance")
        return SynthesisRecord(
            project_id=envelope.project_id,
            input_refs=envelope.source_ids,
            candidates=tuple(candidates),
            trigger_ref=envelope.trigger_ref,
            synthesis_kind=envelope.synthesis_kind,
        )
