from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

import pytest

from agent_core.experience_store import (
    ISSUE117_EXPERIENCE_ID,
    hydrate_from_one,
    promote_issue117_regression_evidence,
)


def _write(path: Path, value: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _accepted(root: Path) -> None:
    _write(
        root / "experience" / "agentos-core" / "accepted.json",
        {
            "schema": "agentos.experience-set/v0",
            "project_id": "agentos-core",
            "artifacts": [
                {
                    "schema": "agentos.experience/v0",
                    "experience_id": "core.branch-authority.v2",
                    "project_id": "agentos-core",
                    "kind": "decision",
                    "summary": "Core development uses core/integration.",
                    "payload": {"canonical_development_branch": "core/integration"},
                    "provenance": {"sources": ["test://seed"], "accepted_evidence": []},
                    "authority": {"status": "accepted", "supersedes": [], "superseded_by": []},
                    "validity": {"conditions": [], "invalidated_by": []},
                    "realm_scope": ["*"],
                    "capability_scope": ["agentos.core.develop"],
                    "executor_scope": ["*"],
                }
            ],
        },
    )


def _evidence(path: Path, *, verdict: str = "PASS", regressed: list[str] | None = None) -> Path:
    return _write(
        path,
        {
            "schema": "agentos.experience-regression/v1",
            "experiment_id": path.stem,
            "project_id": "agentos-core",
            "executor": "openai-codex-local",
            "verdict": verdict,
            "classification": "EXPERIENCE_REGRESSION_PASS" if verdict == "PASS" else "EXPERIENCE_MASTER_FLOOR_NOT_MET",
            "credential_exposed": False,
            "checks": {
                "hydration_receipt_ok": True,
                "uplift_requirement_met": True,
                "no_regressed_dimensions": not bool(regressed),
                "critical_governance_pass": True,
            },
            "baseline": {"score": {"score": 6 / 7}},
            "hydrated": {"score": {"score": 1.0}},
            "uplift": 1 / 7,
            "required_uplift": 1 / 7,
            "improved_dimensions": ["canonical_development_branch"],
            "regressed_dimensions": regressed or [],
        },
    )


def _authority(evidence: Path) -> dict:
    return {
        "schema": "agentos.experience-promotion-authority/v1",
        "project_id": "agentos-core",
        "approved": True,
        "approved_by": "test-human-authority",
        "evidence_sha256": "sha256:" + sha256(evidence.read_bytes()).hexdigest(),
    }


def test_promotes_verified_evidence_and_hydration_exposes_before_after_delta(tmp_path: Path):
    _accepted(tmp_path)
    evidence = _evidence(tmp_path / "projects" / "agentos-core" / "evidence" / "run.json")
    before = hydrate_from_one(
        project_id="agentos-core", active_goal="continue", realm="oracle", capabilities=("agentos.core.develop",), executor="codex", data_root=tmp_path
    )

    receipt = promote_issue117_regression_evidence(evidence, _authority(evidence), data_root=tmp_path)
    after = hydrate_from_one(
        project_id="agentos-core", active_goal="continue", realm="oracle", capabilities=("agentos.core.develop",), executor="codex", data_root=tmp_path
    )

    assert receipt["promoted"] is True
    assert receipt["credential_exposed"] is False
    assert ISSUE117_EXPERIENCE_ID not in before["experience_ids"]
    assert ISSUE117_EXPERIENCE_ID in after["experience_ids"]
    assert before["digest"] != after["digest"]


def test_promotion_is_idempotent_for_the_same_evidence(tmp_path: Path):
    _accepted(tmp_path)
    evidence = _evidence(tmp_path / "projects" / "agentos-core" / "evidence" / "evidence.json")
    first = promote_issue117_regression_evidence(evidence, _authority(evidence), data_root=tmp_path)
    second = promote_issue117_regression_evidence(evidence, _authority(evidence), data_root=tmp_path)

    assert first["promoted"] is True
    assert second["promoted"] is False
    assert second["before_digest"] == second["after_digest"]


@pytest.mark.parametrize("verdict,regressed", [("FAIL", []), ("PASS", ["canonical_development_branch"])])
def test_rejects_unverified_or_regressed_evidence(tmp_path: Path, verdict: str, regressed: list[str]):
    _accepted(tmp_path)
    evidence = _evidence(tmp_path / "projects" / "agentos-core" / "evidence" / "evidence.json", verdict=verdict, regressed=regressed)

    with pytest.raises(ValueError):
        promote_issue117_regression_evidence(evidence, _authority(evidence), data_root=tmp_path)


def test_rejects_authority_receipt_bound_to_another_evidence_file(tmp_path: Path):
    _accepted(tmp_path)
    evidence = _evidence(tmp_path / "projects" / "agentos-core" / "evidence" / "evidence.json")
    other = _evidence(tmp_path / "projects" / "agentos-core" / "evidence" / "other.json")

    with pytest.raises(ValueError, match="bound to this evidence"):
        promote_issue117_regression_evidence(evidence, _authority(other), data_root=tmp_path)


def test_rejects_evidence_outside_the_project_data_layer(tmp_path: Path):
    _accepted(tmp_path)
    evidence = _evidence(tmp_path / "untrusted-evidence.json")

    with pytest.raises(ValueError, match="data-layer evidence directory"):
        promote_issue117_regression_evidence(evidence, _authority(evidence), data_root=tmp_path)
