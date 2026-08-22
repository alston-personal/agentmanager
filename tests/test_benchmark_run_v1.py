from runtime_core.benchmark_run_v1 import (
    BenchmarkRun,
    EvaluatorCondition,
    ModelCondition,
    RawTaskResult,
    comparable_fixed_model,
)


def model(version="2026-08-22"):
    return ModelCondition(
        provider="provider:test",
        model="model:fixed",
        version=version,
        decoding_policy_ref="decode:deterministic-v1",
        tool_policy_ref="tools:read-only-v1",
    )


def evaluator(version="v1"):
    return EvaluatorCondition(
        evaluator_ref="evaluator:lccb",
        version=version,
        rubric_ref="rubric:lccb-v1",
    )


def run(stage="age-0", model_condition=None, evaluator_condition=None):
    return BenchmarkRun(
        benchmark_id="bench_lccb",
        stage_key=stage,
        snapshot_ref=f"cogsnap:{stage}",
        model_condition=model_condition or model(),
        evaluator_condition=evaluator_condition or evaluator(),
        task_results=(
            RawTaskResult(
                task_key="recall-1",
                response_ref=f"artifact:{stage}:recall-1",
                response_hash="abc123",
                observation_ref=f"observation:{stage}:recall-1",
                started_at="2026-08-22T00:00:00Z",
                completed_at="2026-08-22T00:00:01Z",
            ),
        ),
        experience_manifest_ref=f"experience-manifest:{stage}",
        started_at="2026-08-22T00:00:00Z",
        completed_at="2026-08-22T00:00:02Z",
        seed=1,
    )


def test_run_is_content_addressed_and_records_conditions():
    item = run()
    payload = item.to_dict()
    assert payload["run_id"] == item.run_id
    assert payload["model_condition_id"] == item.model_condition.condition_id
    assert payload["evaluator_condition_id"] == item.evaluator_condition.condition_id


def test_fixed_model_comparison_requires_same_model_and_evaluator_conditions():
    before = run("age-0")
    after = run("age-100")
    assert comparable_fixed_model(before, after)

    changed_model = run("age-100", model_condition=model(version="different"))
    assert not comparable_fixed_model(before, changed_model)

    changed_evaluator = run("age-100", evaluator_condition=evaluator(version="v2"))
    assert not comparable_fixed_model(before, changed_evaluator)


def test_duplicate_task_results_fail_closed():
    result = RawTaskResult(
        task_key="same",
        response_ref="artifact:a",
        response_hash="hash",
        observation_ref="obs:a",
        started_at="t0",
        completed_at="t1",
    )
    try:
        BenchmarkRun(
            benchmark_id="bench",
            stage_key="age-0",
            snapshot_ref="snap",
            model_condition=model(),
            evaluator_condition=evaluator(),
            task_results=(result, result),
            experience_manifest_ref="manifest",
            started_at="t0",
            completed_at="t1",
        )
    except ValueError as exc:
        assert "unique" in str(exc)
    else:
        raise AssertionError("duplicate benchmark task results must fail closed")
