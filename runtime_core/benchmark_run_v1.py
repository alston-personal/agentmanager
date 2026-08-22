"""Reproducible run artifacts for longitudinal AgentOS experiments.

A benchmark run records the concrete model/evaluator/snapshot/task inputs used to
produce observations.  It is evidence metadata only and grants no AgentOS
authority.  Content addressing prevents accidentally comparing results whose
experimental conditions differ.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from hashlib import sha256
import json
from typing import Any


RUN_SCHEMA = "agentos.longitudinal-run/v1"


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _id(prefix: str, payload: dict[str, Any]) -> str:
    return f"{prefix}_{sha256(_canonical(payload).encode('utf-8')).hexdigest()[:32]}"


@dataclass(frozen=True)
class ModelCondition:
    provider: str
    model: str
    version: str
    decoding_policy_ref: str
    tool_policy_ref: str

    def __post_init__(self) -> None:
        for value in asdict(self).values():
            if not str(value).strip():
                raise ValueError("model condition fields are required")

    @property
    def condition_id(self) -> str:
        return _id("modelcond", asdict(self))


@dataclass(frozen=True)
class EvaluatorCondition:
    evaluator_ref: str
    version: str
    rubric_ref: str

    def __post_init__(self) -> None:
        if not self.evaluator_ref.strip() or not self.version.strip() or not self.rubric_ref.strip():
            raise ValueError("evaluator condition fields are required")

    @property
    def condition_id(self) -> str:
        return _id("evalcond", asdict(self))


@dataclass(frozen=True)
class RawTaskResult:
    task_key: str
    response_ref: str
    response_hash: str
    observation_ref: str
    started_at: str
    completed_at: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        required = (
            self.task_key,
            self.response_ref,
            self.response_hash,
            self.observation_ref,
            self.started_at,
            self.completed_at,
        )
        if any(not str(value).strip() for value in required):
            raise ValueError("raw task result identity fields are required")


@dataclass(frozen=True)
class BenchmarkRun:
    benchmark_id: str
    stage_key: str
    snapshot_ref: str
    model_condition: ModelCondition
    evaluator_condition: EvaluatorCondition
    task_results: tuple[RawTaskResult, ...]
    experience_manifest_ref: str
    started_at: str
    completed_at: str
    seed: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: str = RUN_SCHEMA

    def __post_init__(self) -> None:
        required = (
            self.benchmark_id,
            self.stage_key,
            self.snapshot_ref,
            self.experience_manifest_ref,
            self.started_at,
            self.completed_at,
        )
        if any(not str(value).strip() for value in required):
            raise ValueError("benchmark run identity fields are required")
        keys = [item.task_key for item in self.task_results]
        if len(set(keys)) != len(keys):
            raise ValueError("benchmark run task keys must be unique")

    @property
    def run_id(self) -> str:
        return _id("benchrun", asdict(self))

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["model_condition_id"] = self.model_condition.condition_id
        value["evaluator_condition_id"] = self.evaluator_condition.condition_id
        value["run_id"] = self.run_id
        return value


def comparable_fixed_model(left: BenchmarkRun, right: BenchmarkRun) -> bool:
    """Whether two runs satisfy the fixed-model comparison condition."""
    return (
        left.benchmark_id == right.benchmark_id
        and left.model_condition.condition_id == right.model_condition.condition_id
        and left.evaluator_condition.condition_id == right.evaluator_condition.condition_id
    )
