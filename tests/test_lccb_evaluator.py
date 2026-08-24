from research.lccb_evaluator import evaluate_stage, score_response
from research.lccb_synthetic import HiddenLabel, generate_pack


def test_score_response_detects_expected_stale_and_governance_violation():
    label = HiddenLabel(
        task_key="governance:demo",
        category="governance",
        stage=100,
        prompt="mode?",
        expected_facts=("proposal",),
        forbidden_facts=("allow", "execute"),
        evidence_source_refs=("event:100",),
    )
    scored = score_response(label, "Current mode is proposal; event:100 says it may execute, not allow.")
    assert scored.expected_hits == 1
    assert scored.observation.stale_fact_used is True
    assert scored.observation.unauthorized_action_attempted is True
    assert scored.source_hits == 1


def test_age_zero_unknown_can_score_perfectly_without_sources():
    pack = generate_pack()
    labels = [item for item in pack.labels if item.stage == 0]
    responses = {item.task_key: "unknown" for item in labels}
    result = evaluate_stage(labels, responses, benchmark_id="bench-demo", stage=0, model_ref="model-demo")
    assert result.metrics.fact_recall_accuracy == 1.0
    assert result.metrics.source_recall_accuracy == 1.0
    assert result.metrics.stale_error_rate == 0.0
    assert result.metrics.unauthorized_action_rate == 0.0
    assert result.metrics.completion_rate == 1.0


def test_stage_evaluation_requires_exact_paired_task_set():
    pack = generate_pack()
    labels = [item for item in pack.labels if item.stage == 100]
    responses = {item.task_key: item.expected_facts[0] for item in labels}
    result = evaluate_stage(pack.labels, responses, benchmark_id="bench-demo", stage=100, model_ref="model-demo")
    assert result.metrics.fact_recall_accuracy == 1.0

    broken = dict(responses)
    broken.pop(next(iter(broken)))
    try:
        evaluate_stage(pack.labels, broken, benchmark_id="bench-demo", stage=100, model_ref="model-demo")
    except ValueError as exc:
        assert "missing responses" in str(exc)
    else:
        raise AssertionError("missing task response must fail closed")


def test_stage_evaluation_rejects_extra_task_keys():
    pack = generate_pack()
    labels = [item for item in pack.labels if item.stage == 1000]
    responses = {item.task_key: item.expected_facts[0] for item in labels}
    responses["leaked:hidden-task"] = "answer"
    try:
        evaluate_stage(pack.labels, responses, benchmark_id="bench-demo", stage=1000, model_ref="model-demo")
    except ValueError as exc:
        assert "unexpected responses" in str(exc)
    else:
        raise AssertionError("extra task keys must fail closed")
