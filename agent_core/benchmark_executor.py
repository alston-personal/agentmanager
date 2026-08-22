"""Provider-neutral execution contract for longitudinal benchmark tasks.

This module does not choose or invoke a production model by itself. A concrete
adapter supplies the response function and artifact persistence boundary. The
runner only enforces experiment identity, task ordering, response hashing and
raw-result completeness.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Callable, Protocol

from runtime_core.benchmark_run_v1 import (
    BenchmarkRun,
    EvaluatorCondition,
    ModelCondition,
    RawTaskResult,
)
from runtime_core.benchmark_v1 import BenchmarkStage, BenchmarkTask, LongitudinalBenchmark


@dataclass(frozen=True)
class ExecutedResponse:
    response_text: str
    response_ref: str
    observation_ref: str
    started_at: str
    completed_at: str

    def __post_init__(self) -> None:
        if not self.response_ref.strip() or not self.observation_ref.strip():
            raise ValueError("response_ref and observation_ref are required")
        if not self.started_at.strip() or not self.completed_at.strip():
            raise ValueError("execution timestamps are required")


class BenchmarkTaskExecutor(Protocol):
    def __call__(self, task: BenchmarkTask, stage: BenchmarkStage) -> ExecutedResponse: ...


def execute_benchmark_stage(
    benchmark: LongitudinalBenchmark,
    *,
    stage_key: str,
    model_condition: ModelCondition,
    evaluator_condition: EvaluatorCondition,
    experience_manifest_ref: str,
    started_at: str,
    completed_at: str,
    executor: BenchmarkTaskExecutor,
    seed: int | None = None,
) -> BenchmarkRun:
    """Execute tasks in stable task-key order and return raw run evidence.

    Scoring is intentionally separate: the executor cannot declare its own
    success metrics, and the evaluator cannot silently change model conditions.
    """
    stages = {stage.stage_key: stage for stage in benchmark.stages}
    stage = stages.get(stage_key)
    if stage is None:
        raise KeyError(stage_key)
    if not experience_manifest_ref.strip():
        raise ValueError("experience_manifest_ref is required")

    results: list[RawTaskResult] = []
    for task in sorted(benchmark.tasks, key=lambda item: item.task_key):
        response = executor(task, stage)
        digest = sha256(response.response_text.encode("utf-8")).hexdigest()
        results.append(
            RawTaskResult(
                task_key=task.task_key,
                response_ref=response.response_ref,
                response_hash=digest,
                observation_ref=response.observation_ref,
                started_at=response.started_at,
                completed_at=response.completed_at,
            )
        )

    return BenchmarkRun(
        benchmark_id=benchmark.benchmark_id,
        stage_key=stage.stage_key,
        snapshot_ref=stage.snapshot_ref,
        model_condition=model_condition,
        evaluator_condition=evaluator_condition,
        task_results=tuple(results),
        experience_manifest_ref=experience_manifest_ref,
        started_at=started_at,
        completed_at=completed_at,
        seed=seed,
    )
