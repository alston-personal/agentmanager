from hashlib import sha256

from agent_core.benchmark_executor import ExecutedResponse, execute_benchmark_stage
from runtime_core.benchmark_run_v1 import EvaluatorCondition, ModelCondition
from runtime_core.benchmark_v1 import BenchmarkStage, BenchmarkTask, LongitudinalBenchmark


def benchmark():
    return LongitudinalBenchmark(
        name="executor-smoke",
        tasks=(
            BenchmarkTask("b-task", "recall", "B?"),
            BenchmarkTask("a-task", "recall", "A?"),
        ),
        stages=(BenchmarkStage("age-0", 0, "cogsnap:0"),),
    )


def model():
    return ModelCondition(
        provider="provider:test",
        model="model:fixed",
        version="v1",
        decoding_policy_ref="decode:v1",
        tool_policy_ref="tools:readonly",
    )


def evaluator():
    return EvaluatorCondition("eval:test", "v1", "rubric:v1")


def test_executor_runs_tasks_in_stable_order_and_hashes_raw_response():
    calls = []

    def execute(task, stage):
        calls.append((task.task_key, stage.stage_key))
        text = f"answer:{task.task_key}"
        return ExecutedResponse(
            response_text=text,
            response_ref=f"artifact:{task.task_key}",
            observation_ref=f"observation:{task.task_key}",
            started_at="t0",
            completed_at="t1",
        )

    run = execute_benchmark_stage(
        benchmark(),
        stage_key="age-0",
        model_condition=model(),
        evaluator_condition=evaluator(),
        experience_manifest_ref="manifest:0",
        started_at="t0",
        completed_at="t2",
        executor=execute,
        seed=1,
    )
    assert calls == [("a-task", "age-0"), ("b-task", "age-0")]
    assert [item.task_key for item in run.task_results] == ["a-task", "b-task"]
    assert run.task_results[0].response_hash == sha256(b"answer:a-task").hexdigest()
    assert run.snapshot_ref == "cogsnap:0"


def test_executor_rejects_unknown_stage_before_calling_provider():
    called = False

    def execute(task, stage):
        nonlocal called
        called = True
        raise AssertionError("must not execute")

    try:
        execute_benchmark_stage(
            benchmark(),
            stage_key="missing",
            model_condition=model(),
            evaluator_condition=evaluator(),
            experience_manifest_ref="manifest:0",
            started_at="t0",
            completed_at="t1",
            executor=execute,
        )
    except KeyError as exc:
        assert "missing" in str(exc)
    else:
        raise AssertionError("unknown stage must fail")
    assert called is False


def test_executor_requires_experience_manifest():
    try:
        execute_benchmark_stage(
            benchmark(),
            stage_key="age-0",
            model_condition=model(),
            evaluator_condition=evaluator(),
            experience_manifest_ref="",
            started_at="t0",
            completed_at="t1",
            executor=lambda task, stage: None,
        )
    except ValueError as exc:
        assert "experience_manifest" in str(exc)
    else:
        raise AssertionError("missing experience manifest must fail closed")
