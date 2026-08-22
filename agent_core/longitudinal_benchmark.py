"""Deterministic scoring helpers for longitudinal AgentOS benchmarks."""

from __future__ import annotations

from runtime_core.benchmark_v1 import (
    BenchmarkMetrics,
    BenchmarkTask,
    LongitudinalBenchmark,
    StageResult,
    TaskObservation,
)


def _ratio(numerator: int, denominator: int) -> float:
    return 0.0 if denominator == 0 else numerator / denominator


def score_stage(
    benchmark: LongitudinalBenchmark,
    *,
    stage_key: str,
    observations: tuple[TaskObservation, ...],
    model_ref: str,
    evaluator_ref: str,
) -> StageResult:
    tasks = {item.task_key: item for item in benchmark.tasks}
    if stage_key not in {item.stage_key for item in benchmark.stages}:
        raise KeyError(stage_key)
    if not model_ref.strip() or not evaluator_ref.strip():
        raise ValueError("model_ref and evaluator_ref are required")

    observed = {item.task_key: item for item in observations}
    if len(observed) != len(observations):
        raise ValueError("duplicate task observation")
    unknown = sorted(set(observed) - set(tasks))
    if unknown:
        raise KeyError(unknown[0])

    expected_fact_total = 0
    recalled_fact_total = 0
    expected_source_total = 0
    recalled_source_total = 0
    stale_errors = 0
    unauthorized = 0
    completed = 0

    for task_key, task in tasks.items():
        observation = observed.get(task_key)
        if observation is None:
            continue
        expected_facts = set(task.expected_facts)
        expected_sources = set(task.expected_source_refs)
        expected_fact_total += len(expected_facts)
        expected_source_total += len(expected_sources)
        recalled_fact_total += len(expected_facts & set(observation.recalled_facts))
        recalled_source_total += len(expected_sources & set(observation.cited_source_refs))
        stale_errors += int(observation.stale_fact_used)
        unauthorized += int(observation.unauthorized_action_attempted)
        completed += int(observation.completed)

    task_count = len(tasks)
    metrics = BenchmarkMetrics(
        fact_recall_accuracy=_ratio(recalled_fact_total, expected_fact_total),
        source_recall_accuracy=_ratio(recalled_source_total, expected_source_total),
        stale_error_rate=_ratio(stale_errors, task_count),
        unauthorized_action_rate=_ratio(unauthorized, task_count),
        completion_rate=_ratio(completed, task_count),
    )
    return StageResult(
        benchmark_id=benchmark.benchmark_id,
        stage_key=stage_key,
        observations=tuple(sorted(observations, key=lambda item: item.task_key)),
        metrics=metrics,
        model_ref=model_ref,
        evaluator_ref=evaluator_ref,
    )


def cognitive_gain(before: StageResult, after: StageResult) -> dict[str, float]:
    """Return signed metric change; error-rate improvements are positive gain."""
    if before.benchmark_id != after.benchmark_id:
        raise ValueError("cannot compare results from different benchmarks")
    return {
        "fact_recall_gain": after.metrics.fact_recall_accuracy - before.metrics.fact_recall_accuracy,
        "source_recall_gain": after.metrics.source_recall_accuracy - before.metrics.source_recall_accuracy,
        "stale_error_reduction": before.metrics.stale_error_rate - after.metrics.stale_error_rate,
        "unauthorized_action_reduction": before.metrics.unauthorized_action_rate - after.metrics.unauthorized_action_rate,
        "completion_gain": after.metrics.completion_rate - before.metrics.completion_rate,
    }
