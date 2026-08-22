from research.lccb_baselines import run_controlled_baselines
from research.lccb_synthetic import generate_pack


def test_controlled_baselines_show_supersession_gap():
    result = run_controlled_baselines(generate_pack())
    unknown = result["baselines"]["always_unknown"]
    first = result["baselines"]["first_observed"]
    latest = result["baselines"]["latest_structured"]

    assert unknown["0"]["fact_recall_accuracy"] == 1.0
    assert unknown["100"]["fact_recall_accuracy"] == 0.0
    assert latest["100"]["fact_recall_accuracy"] == 1.0
    assert latest["1000"]["fact_recall_accuracy"] == 1.0
    assert latest["1000"]["stale_error_rate"] == 0.0

    assert first["100"]["fact_recall_accuracy"] == 1.0
    assert first["1000"]["fact_recall_accuracy"] < latest["1000"]["fact_recall_accuracy"]
    assert first["1000"]["stale_error_rate"] > 0.0


def test_baseline_result_is_dataset_identified():
    result = run_controlled_baselines(generate_pack())
    assert result["schema_version"] == "agentos.lccb-baseline-results/v1"
    assert len(result["experience_manifest_hash"]) == 64
    assert len(result["evaluator_manifest_hash"]) == 64
