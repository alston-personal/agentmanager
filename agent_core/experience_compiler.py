"""Experience compiler boundary for AgentOS Cognitive Kernel.

Vendor adapters normalize raw activity to ExperienceEvent. A pluggable extractor
may classify observations/decisions/failures/lessons, but AgentOS reattaches
source provenance and forces all extracted knowledge to remain candidates.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable, Sequence

from runtime_core.cognitive_ir import EvidenceRef, KnowledgeCandidate, merge_evidence
from runtime_core.experience_ir import ExperienceBatch, ExperienceEvent


@dataclass(frozen=True)
class ExperienceCompilationEnvelope:
    project_id: str
    event_ids: tuple[str, ...]
    events: tuple[ExperienceEvent, ...]
    required_output_kinds: tuple[str, ...] = (
        "observation",
        "decision",
        "hypothesis",
        "rejected_idea",
        "constraint",
        "failure",
        "lesson",
        "open_question",
    )
    rules: tuple[str, ...] = (
        "extract_only_supported_claims",
        "preserve_uncertainty",
        "do_not_promote_to_truth",
        "retain_source_event_provenance",
        "distinguish_observation_from_inference",
    )


class ExperienceCompilerBoundary:
    """Builds bounded extraction input and governs extracted candidates."""

    def build_envelope(self, batch: ExperienceBatch) -> ExperienceCompilationEnvelope:
        return ExperienceCompilationEnvelope(
            project_id=batch.project_id,
            event_ids=batch.event_ids,
            events=batch.events,
        )

    def normalize_candidate(
        self,
        envelope: ExperienceCompilationEnvelope,
        proposed: KnowledgeCandidate,
        *,
        supporting_event_ids: Sequence[str],
    ) -> KnowledgeCandidate:
        event_by_id = {item.event_id: item for item in envelope.events}
        supporting_ids = tuple(dict.fromkeys(str(item) for item in supporting_event_ids))
        if not supporting_ids:
            raise ValueError("compiled knowledge requires at least one supporting event")
        missing = [item for item in supporting_ids if item not in event_by_id]
        if missing:
            raise ValueError("unknown supporting experience event: " + ", ".join(missing))

        evidence = []
        for event_id in supporting_ids:
            event = event_by_id[event_id]
            evidence.append(
                EvidenceRef(
                    source_kind=event.source_kind,
                    source_ref=event.source_ref,
                    content_hash=event.content_hash,
                    relation="supports",
                    trust_class=event.trust_class,
                )
            )

        metadata = dict(proposed.metadata)
        metadata.update(
            {
                "experience_event_ids": list(supporting_ids),
                "compiled_from_experience": True,
                "governance_state": "candidate",
            }
        )
        return replace(
            proposed,
            project_id=envelope.project_id,
            status="candidate",
            abstraction_level="working",
            evidence=merge_evidence(evidence, proposed.evidence),
            derived_from=tuple(dict.fromkeys([*supporting_ids, *proposed.derived_from])),
            metadata=metadata,
        )


def group_events_for_compaction(
    events: Sequence[ExperienceEvent],
    *,
    max_events: int = 50,
) -> tuple[tuple[ExperienceEvent, ...], ...]:
    """Deterministic bounded batching; token-aware backends may replace this later."""
    if max_events < 1:
        raise ValueError("max_events must be positive")
    return tuple(
        tuple(events[index : index + max_events])
        for index in range(0, len(events), max_events)
    )
