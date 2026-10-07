from pathlib import Path

from agent_core.growth_auditor import GrowthAuditor


def test_reuse_without_counterfactual_is_g2(tmp_path: Path):
    auditor = GrowthAuditor(tmp_path)
    result = auditor.observe(
        {
            "source_experience": ["wardrobe-runtime:v1"],
            "new_task": "new runtime integration",
            "candidate_id": "runtime-session-pattern",
            "independent_reuse": True,
            "reuse_boundary": "same-node",
            "evidence": ["receipt://new-runtime/1"],
        }
    )
    assert result["qualified"] is True
    assert result["proof"]["verdict"] == "G2"


def test_measured_uplift_is_g3(tmp_path: Path):
    auditor = GrowthAuditor(tmp_path)
    result = auditor.observe(
        {
            "source_experience": ["wardrobe-runtime:v1"],
            "new_task": "new runtime integration",
            "candidate_id": "runtime-session-pattern",
            "independent_reuse": True,
            "reuse_boundary": "same-node",
            "metrics_before": {"human_interventions": 4, "iterations": 12},
            "metrics_after": {"human_interventions": 1, "iterations": 4},
            "evidence": ["receipt://before", "receipt://after"],
        }
    )
    assert result["proof"]["verdict"] == "G3"
    assert result["proof"]["uplift"]["human_interventions"] == -3.0


def test_cross_executor_measured_transfer_is_g4(tmp_path: Path):
    auditor = GrowthAuditor(tmp_path)
    result = auditor.observe(
        {
            "source_experience": ["wardrobe-runtime:v1"],
            "new_task": "participant runtime",
            "candidate_id": "runtime-session-pattern",
            "independent_reuse": True,
            "reuse_boundary": "cross-executor",
            "metrics_before": {"success_rate": 0.5},
            "metrics_after": {"success_rate": 0.9},
        }
    )
    assert result["proof"]["verdict"] == "G4"


def test_same_evidence_is_deduplicated(tmp_path: Path):
    auditor = GrowthAuditor(tmp_path)
    observation = {
        "source_experience": ["wardrobe-runtime:v1"],
        "new_task": "new runtime",
        "candidate_id": "runtime-session-pattern",
        "independent_reuse": True,
    }
    first = auditor.observe(observation)
    second = auditor.observe(observation)
    assert first["deduplicated"] is False
    assert second["deduplicated"] is True
    ledger = auditor.load()
    assert ledger["metrics"]["qualified_total"] == 1
