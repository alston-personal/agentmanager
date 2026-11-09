"""Deterministic baselines for the controlled LCCB track.

These are research comparators, not AgentOS runtime components. They consume
only public experience plus public task keys/prompts. Hidden labels are used
only by the evaluator after responses have been produced.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Iterable

from research.lccb_evaluator import evaluate_stage
from research.lccb_synthetic import HiddenLabel, SyntheticPack
from runtime_core.experience_ir import ExperienceEvent


def _visible(events: Iterable[ExperienceEvent], stage: int) -> tuple[ExperienceEvent, ...]:
    return tuple(event for event in events if int(event.metadata.get("sequence", 0)) <= stage)


def _render_event_value(event: ExperienceEvent) -> str:
    op = event.metadata.get("op")
    if op == "set_fact":
        return str(event.metadata["value"])
    if op == "set_procedure":
        return " -> ".join(str(item) for item in event.metadata["steps"])
    if op in {"set_capability", "set_work"}:
        return str(event.metadata["value"])
    return "unknown"


def _matching_events(events: tuple[ExperienceEvent, ...], task_key: str) -> tuple[ExperienceEvent, ...]:
    if task_key.startswith("state:"):
        key = task_key.removeprefix("state:")
        return tuple(event for event in events if event.metadata.get("op") == "set_fact" and event.metadata.get("key") == key)
    if task_key.startswith("procedure:"):
        key = task_key.removeprefix("procedure:")
        return tuple(event for event in events if event.metadata.get("op") == "set_procedure" and event.metadata.get("key") == key)
    if task_key.startswith("governance:"):
        key = task_key.removeprefix("governance:")
        return tuple(event for event in events if event.metadata.get("op") == "set_capability" and event.metadata.get("key") == key)
    return ()


def always_unknown(pack: SyntheticPack, stage: int) -> dict[str, str]:
    labels = [item for item in pack.labels if item.stage == stage]
    return {item.task_key: "unknown" for item in labels}


def observed_baseline(pack: SyntheticPack, stage: int, *, latest: bool) -> dict[str, str]:
    events = _visible(pack.events, stage)
    labels = [item for item in pack.labels if item.stage == stage]
    responses: dict[str, str] = {}
    for label in labels:
        if label.task_key == "continuity:next-work":
            work_events = tuple(event for event in events if event.metadata.get("op") == "set_work")
            if not work_events:
                responses[label.task_key] = "unknown"
                continue
            if latest:
                status: dict[str, tuple[str, str]] = {}
                for event in work_events:
                    status[str(event.metadata["key"])] = (str(event.metadata["value"]), event.source_ref)
                ready = sorted(key for key, (value, _) in status.items() if value == "ready")
                answer = ready[0] if ready else "no_ready_work"
                refs = " ".join(ref for _, ref in status.values())
                responses[label.task_key] = f"{answer} {refs}"
            else:
                first_ready = next((event for event in work_events if event.metadata.get("value") == "ready"), None)
                if first_ready is None:
                    responses[label.task_key] = "no_ready_work"
                else:
                    responses[label.task_key] = f"{first_ready.metadata['key']} {first_ready.source_ref}"
            continue

        matches = _matching_events(events, label.task_key)
        if not matches:
            responses[label.task_key] = "unknown"
            continue
        event = matches[-1] if latest else matches[0]
        responses[label.task_key] = f"{_render_event_value(event)} {event.source_ref}"
    return responses


def run_controlled_baselines(pack: SyntheticPack, *, benchmark_id: str = "lccb-controlled-v1") -> dict:
    baselines = {
        "always_unknown": lambda stage: always_unknown(pack, stage),
        "first_observed": lambda stage: observed_baseline(pack, stage, latest=False),
        "latest_structured": lambda stage: observed_baseline(pack, stage, latest=True),
    }
    result: dict[str, object] = {
        "schema_version": "agentos.lccb-baseline-results/v1",
        "seed": pack.seed,
        "experience_manifest_hash": pack.experience_manifest_hash,
        "evaluator_manifest_hash": pack.evaluator_manifest_hash,
        "baselines": {},
    }
    for name, response_fn in baselines.items():
        stages: dict[str, object] = {}
        for stage in (0, 100, 1000):
            scored = evaluate_stage(
                pack.labels,
                response_fn(stage),
                benchmark_id=benchmark_id,
                stage=stage,
                model_ref=f"deterministic:{name}",
            )
            stages[str(stage)] = asdict(scored.metrics)
        result["baselines"][name] = stages
    return result
