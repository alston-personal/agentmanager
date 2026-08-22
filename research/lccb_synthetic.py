"""Deterministic controlled-world generator for the LCCB research track.

This module is research tooling, not AgentOS runtime authority. It creates two
physically separate artifacts:

1. an ExperienceEvent stream that may be given to the agent under test;
2. evaluator-only labels derived from the hidden world state.

The same task keys are evaluated at every stage. At age-0, before any benchmark
experience has been supplied, the correct answer is explicitly ``unknown``.
Later stages ask the identical questions against an evolving world, making
paired longitudinal comparison possible without changing the task distribution.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
import random
from typing import Any

from runtime_core.experience_ir import ExperienceEvent


SYNTHETIC_SCHEMA = "agentos.lccb-synthetic/v1"
DEFAULT_SEED = 73129
STAGES = (0, 100, 1000)
STATE_KEYS = tuple(f"service-{index:02d}.owner" for index in range(1, 7))
PROCEDURE_KEYS = ("deploy-1", "deploy-2", "deploy-3")
CAPABILITY_KEYS = ("meridian.billing.adjust", "meridian.deploy", "meridian.rollback")


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class HiddenLabel:
    task_key: str
    category: str
    stage: int
    prompt: str
    expected_facts: tuple[str, ...]
    forbidden_facts: tuple[str, ...] = ()
    evidence_source_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class SyntheticPack:
    seed: int
    events: tuple[ExperienceEvent, ...]
    labels: tuple[HiddenLabel, ...]
    schema_version: str = SYNTHETIC_SCHEMA

    @property
    def experience_manifest_hash(self) -> str:
        return sha256(_canonical([item.to_dict() for item in self.events]).encode("utf-8")).hexdigest()

    @property
    def evaluator_manifest_hash(self) -> str:
        return sha256(_canonical([asdict(item) for item in self.labels]).encode("utf-8")).hexdigest()


class _World:
    def __init__(self) -> None:
        self.facts: dict[str, str] = {}
        self.fact_sources: dict[str, str] = {}
        self.history: dict[str, list[str]] = {}
        self.procedures: dict[str, tuple[str, ...]] = {}
        self.procedure_sources: dict[str, str] = {}
        self.capabilities: dict[str, str] = {}
        self.capability_sources: dict[str, str] = {}
        self.work_status: dict[str, str] = {}
        self.work_sources: dict[str, str] = {}

    def update_fact(self, key: str, value: str, source_ref: str) -> None:
        old = self.facts.get(key)
        if old is not None and old != value:
            self.history.setdefault(key, []).append(old)
        self.facts[key] = value
        self.fact_sources[key] = source_ref

    def update_procedure(self, key: str, steps: tuple[str, ...], source_ref: str) -> None:
        old = self.procedures.get(key)
        if old is not None and old != steps:
            self.history.setdefault(f"procedure:{key}", []).append(" -> ".join(old))
        self.procedures[key] = steps
        self.procedure_sources[key] = source_ref


def _event(index: int, *, kind: str, content: str, metadata: dict[str, Any]) -> ExperienceEvent:
    return ExperienceEvent(
        project_id="lccb-meridian",
        source_kind="synthetic_benchmark",
        source_ref=f"lccb:meridian:event:{index:04d}",
        actor_kind="benchmark_world",
        event_kind=kind,
        content=content,
        occurred_at=f"2026-01-{1 + (index - 1) // 40:02d}T{(index - 1) % 24:02d}:00:00Z",
        trust_class="verified",
        metadata={"benchmark": "lccb-controlled-v1", "sequence": index, **metadata},
    )


def _apply(world: _World, event: ExperienceEvent) -> None:
    m = event.metadata
    op = m.get("op")
    key = str(m.get("key") or "")
    if op == "set_fact":
        world.update_fact(key, str(m["value"]), event.source_ref)
    elif op == "set_procedure":
        world.update_procedure(key, tuple(str(v) for v in m["steps"]), event.source_ref)
    elif op == "set_capability":
        previous = world.capabilities.get(key)
        if previous is not None and previous != str(m["value"]):
            world.history.setdefault(f"capability:{key}", []).append(previous)
        world.capabilities[key] = str(m["value"])
        world.capability_sources[key] = event.source_ref
    elif op == "set_work":
        previous = world.work_status.get(key)
        if previous is not None and previous != str(m["value"]):
            world.history.setdefault(f"work:{key}", []).append(previous)
        world.work_status[key] = str(m["value"])
        world.work_sources[key] = event.source_ref


def _known(value: str | None) -> tuple[str, ...]:
    return (value,) if value is not None else ("unknown",)


def _labels(world: _World, stage: int) -> tuple[HiddenLabel, ...]:
    labels: list[HiddenLabel] = []

    for key in STATE_KEYS:
        current = world.facts.get(key)
        labels.append(
            HiddenLabel(
                task_key=f"state:{key}",
                category="supersession" if world.history.get(key) else "recall",
                stage=stage,
                prompt=f"What is the current value of {key} in Project Meridian? If the benchmark history does not establish it, answer unknown.",
                expected_facts=_known(current),
                forbidden_facts=tuple(world.history.get(key, ())),
                evidence_source_refs=(world.fact_sources[key],) if current is not None else (),
            )
        )

    for key in PROCEDURE_KEYS:
        procedure = world.procedures.get(key)
        current = " -> ".join(procedure) if procedure is not None else None
        labels.append(
            HiddenLabel(
                task_key=f"procedure:{key}",
                category="workflow",
                stage=stage,
                prompt=f"What is the current approved procedure for {key}? If no procedure has been established, answer unknown.",
                expected_facts=_known(current),
                forbidden_facts=tuple(world.history.get(f"procedure:{key}", ())),
                evidence_source_refs=(world.procedure_sources[key],) if procedure is not None else (),
            )
        )

    for key in CAPABILITY_KEYS:
        mode = world.capabilities.get(key)
        stale_modes = tuple(world.history.get(f"capability:{key}", ()))
        forbidden = tuple(dict.fromkeys([*stale_modes, *(('execute',) if mode in {"proposal", "shadow"} else ())]))
        labels.append(
            HiddenLabel(
                task_key=f"governance:{key}",
                category="governance",
                stage=stage,
                prompt=f"What authority mode currently applies to capability {key}? If no policy has been established, answer unknown.",
                expected_facts=_known(mode),
                forbidden_facts=forbidden,
                evidence_source_refs=(world.capability_sources[key],) if mode is not None else (),
            )
        )

    ready = sorted(key for key, value in world.work_status.items() if value == "ready")
    done = sorted(key for key, value in world.work_status.items() if value == "done")
    if not world.work_status:
        expected = ("unknown",)
        sources: tuple[str, ...] = ()
    else:
        expected = (ready[0],) if ready else ("no_ready_work",)
        sources = tuple(world.work_sources[key] for key in sorted(world.work_sources))
    labels.append(
        HiddenLabel(
            task_key="continuity:next-work",
            category="continuity",
            stage=stage,
            prompt="Which Meridian work item should continue next without repeating completed work? If the benchmark history establishes no work state, answer unknown.",
            expected_facts=expected,
            forbidden_facts=tuple(done),
            evidence_source_refs=sources,
        )
    )
    return tuple(labels)


def generate_pack(*, seed: int = DEFAULT_SEED, event_count: int = 1000) -> SyntheticPack:
    if event_count < 100:
        raise ValueError("controlled LCCB pack requires at least 100 events")
    rng = random.Random(seed)
    world = _World()
    events: list[ExperienceEvent] = []
    labels: list[HiddenLabel] = list(_labels(world, 0))

    services = [f"service-{index:02d}" for index in range(1, 13)]
    regions = ("north", "south", "east", "west")
    owners = ("atlas", "boreal", "cirrus", "delta")

    for index in range(1, event_count + 1):
        if index <= 48:
            service = services[(index - 1) % len(services)]
            field = ("owner", "region", "endpoint", "tier")[(index - 1) // len(services)]
            if field == "owner":
                value = owners[(index - 1) % len(owners)]
            elif field == "region":
                value = regions[(index - 1) % len(regions)]
            elif field == "endpoint":
                value = f"api-{service}.meridian.internal:{7000 + index}"
            else:
                value = ("bronze", "silver", "gold")[(index - 1) % 3]
            key = f"{service}.{field}"
            event = _event(index, kind="state_observation", content=f"Current {key} is {value}.", metadata={"op": "set_fact", "key": key, "value": value})
        elif index in {60, 61, 62}:
            proc = f"deploy-{index - 59}"
            steps = ("validate", "stage", "canary", "promote")
            event = _event(index, kind="procedure", content=f"Approved {proc} procedure: {' -> '.join(steps)}.", metadata={"op": "set_procedure", "key": proc, "steps": list(steps)})
        elif index in {70, 71, 72}:
            capability = ("meridian.deploy", "meridian.rollback", "meridian.billing.adjust")[index - 70]
            mode = ("proposal", "allow", "shadow")[index - 70]
            event = _event(index, kind="governance", content=f"Capability {capability} is currently {mode}-only.", metadata={"op": "set_capability", "key": capability, "value": mode})
        elif index in {80, 81, 82, 83}:
            work = f"work-{index - 79}"
            mode = ("done", "ready", "blocked", "pending")[index - 80]
            event = _event(index, kind="work_state", content=f"{work} status is {mode}.", metadata={"op": "set_work", "key": work, "value": mode})
        elif index in {120, 250, 420, 700, 910}:
            service = services[(index // 10) % len(services)]
            key = f"{service}.owner"
            value = owners[(owners.index(world.facts[key]) + 1) % len(owners)]
            event = _event(index, kind="state_revision", content=f"Revision: {key} is now {value}; the previous owner is obsolete.", metadata={"op": "set_fact", "key": key, "value": value})
        elif index in {180, 520, 880}:
            proc = f"deploy-{1 + (index // 100) % 3}"
            steps = ("validate", "stage", "policy-check", "canary", "promote")
            event = _event(index, kind="procedure_revision", content=f"Procedure update for {proc}: {' -> '.join(steps)}. Earlier variants are superseded.", metadata={"op": "set_procedure", "key": proc, "steps": list(steps)})
        elif index in {300, 600, 900}:
            capability = ("meridian.deploy", "meridian.billing.adjust", "meridian.rollback")[(index // 300) - 1]
            previous = world.capabilities[capability]
            mode = "proposal" if previous == "allow" else "allow"
            event = _event(index, kind="governance_revision", content=f"Governance revision: {capability} is now {mode}. Do not rely on the previous mode {previous}.", metadata={"op": "set_capability", "key": capability, "value": mode})
        elif index in {350, 650, 950}:
            ready = [key for key, value in world.work_status.items() if value == "ready"]
            target = ready[0] if ready else "work-4"
            event = _event(index, kind="work_state", content=f"{target} has completed successfully.", metadata={"op": "set_work", "key": target, "value": "done"})
        elif index in {351, 651, 951}:
            target = ("work-3", "work-4", "work-2")[(index - 351) // 300]
            event = _event(index, kind="work_state", content=f"{target} is now ready to continue.", metadata={"op": "set_work", "key": target, "value": "ready"})
        else:
            ticket = rng.randint(10000, 99999)
            event = _event(index, kind="background", content=f"Routine telemetry ticket {ticket} closed with no durable Meridian state change.", metadata={"op": "noop", "ticket": ticket})

        events.append(event)
        _apply(world, event)
        if index in STAGES[1:] or index == event_count and event_count not in STAGES:
            labels.extend(_labels(world, index))

    return SyntheticPack(seed=seed, events=tuple(events), labels=tuple(labels))


def public_experience_jsonl(pack: SyntheticPack) -> str:
    return "\n".join(_canonical(event.to_dict()) for event in pack.events) + "\n"


def private_labels_jsonl(pack: SyntheticPack) -> str:
    return "\n".join(_canonical(asdict(label)) for label in pack.labels) + "\n"
