"""Portable benchmark records for longitudinal AgentOS cognition evaluation.

The benchmark schema separates benchmark identity from any concrete model or
provider.  A fixed-model experiment and a cross-model continuity experiment can
therefore consume the same task/stage definitions without making the evaluator
part of AgentOS authority.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from hashlib import sha256
import json
from typing import Any


BENCHMARK_SCHEMA = "agentos.longitudinal-benchmark/v1"
RESULT_SCHEMA = "agentos.longitudinal-result/v1"


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _id(prefix: str, payload: dict[str, Any]) -> str:
    return f"{prefix}_{sha256(_canonical(payload).encode('utf-8')).hexdigest()[:32]}"


@dataclass(frozen=True)
class BenchmarkTask:
    task_key: str
    category: str
    prompt: str
    expected_facts: tuple[str, ...] = field(default_factory=tuple)
    forbidden_facts: tuple[str, ...] = field(default_factory=tuple)
    expected_source_refs: tuple[str, ...] = field(default_factory=tuple)
    requires_authority: bool = False

    def __post_init__(self) -> None:
        if not self.task_key.strip() or not self.category.strip() or not self.prompt.strip():
            raise ValueError("task_key, category and prompt are required")


@dataclass(frozen=True)
class BenchmarkStage:
    stage_key: str
    experience_count: int
    snapshot_ref: str
    description: str = ""

    def __post_init__(self) -> None:
        if not self.stage_key.strip() or not self.snapshot_ref.strip():
            raise ValueError("stage_key and snapshot_ref are required")
        if self.experience_count < 0:
            raise ValueError("experience_count cannot be negative")


@dataclass(frozen=True)
class LongitudinalBenchmark:
    name: str
    tasks: tuple[BenchmarkTask, ...]
    stages: tuple[BenchmarkStage, ...]
    fixed_model: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: str = BENCHMARK_SCHEMA

    def __post_init__(self) -> None:
        if not self.name.strip() or not self.tasks or not self.stages:
            raise ValueError("benchmark name, tasks and stages are required")
        task_keys = [item.task_key for item in self.tasks]
        stage_keys = [item.stage_key for item in self.stages]
        if len(set(task_keys)) != len(task_keys) or len(set(stage_keys)) != len(stage_keys):
            raise ValueError("benchmark task/stage keys must be unique")
        if list(self.stages) != sorted(self.stages, key=lambda item: (item.experience_count, item.stage_key)):
            raise ValueError("benchmark stages must be ordered by experience_count")

    @property
    def benchmark_id(self) -> str:
        return _id("bench", asdict(self))


@dataclass(frozen=True)
class TaskObservation:
    task_key: str
    stage_key: str
    recalled_facts: tuple[str, ...] = field(default_factory=tuple)
    cited_source_refs: tuple[str, ...] = field(default_factory=tuple)
    unauthorized_action_attempted: bool = False
    stale_fact_used: bool = False
    completed: bool = True


@dataclass(frozen=True)
class BenchmarkMetrics:
    fact_recall_accuracy: float
    source_recall_accuracy: float
    stale_error_rate: float
    unauthorized_action_rate: float
    completion_rate: float

    def __post_init__(self) -> None:
        for name, value in asdict(self).items():
            if not 0.0 <= float(value) <= 1.0:
                raise ValueError(f"{name} must be between 0 and 1")


@dataclass(frozen=True)
class StageResult:
    benchmark_id: str
    stage_key: str
    observations: tuple[TaskObservation, ...]
    metrics: BenchmarkMetrics
    model_ref: str
    evaluator_ref: str
    schema_version: str = RESULT_SCHEMA

    @property
    def result_id(self) -> str:
        return _id("benchresult", asdict(self))
