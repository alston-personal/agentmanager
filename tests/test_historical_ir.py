from __future__ import annotations

import json

import pytest

from agent_core.historical_ir import build_historical_ir, discover_historical_irs, reconcile_historical_irs


def candidate() -> dict:
    return {
        "project_id": "agentos-core",
        "conversation_id": "old-1",
        "source_digest": "sha256:" + "a" * 64,
        "source_files": ["task.md", "walkthrough.md"],
        "signals": {"pass_markers": 1, "fail_markers": 0, "completion_markers": 1, "open_task_markers": 0},
    }


def active() -> dict:
    return {"schema_version": "agentos.ir/v1", "project_id": "agentos-core", "ir_id": "ir-active"}


def test_historical_ir_is_source_bound_and_does_not_copy_conversation():
    record = build_historical_ir(candidate())
    assert record["historical_ir_id"].startswith("hir.agentos-core.old-1.")
    assert record["source"]["raw_conversation_copied"] is False
    assert record["reconciliation"]["automatic_application"] is False


def test_reconcile_returns_derived_candidates_without_mutating_active_ir():
    source = build_historical_ir(candidate())
    result = reconcile_historical_irs(active(), [source], [{
        "historical_ir_id": source["historical_ir_id"], "target_ir_id": "ir-active",
        "relation": "supports", "subject": "The branch decision has historical evidence",
    }])
    assert result["active_ir_mutated"] is False
    assert len(result["context_candidates"]) == 1
    assert result["quarantined"] == []


@pytest.mark.parametrize("relation", ["supersedes", "contradicts"])
def test_replacements_and_conflicts_are_quarantined(relation: str):
    source = build_historical_ir(candidate())
    result = reconcile_historical_irs(active(), [source], [{
        "historical_ir_id": source["historical_ir_id"], "target_ir_id": "ir-active",
        "relation": relation, "subject": "A historical decision",
    }])
    assert result["context_candidates"] == []
    assert result["quarantined"][0]["requires_governed_canonical_advance"] is True


def test_reconcile_rejects_wrong_target():
    source = build_historical_ir(candidate())
    with pytest.raises(ValueError, match="invalid reconciliation assertion"):
        reconcile_historical_irs(active(), [source], [{
            "historical_ir_id": source["historical_ir_id"], "target_ir_id": "old-active",
            "relation": "supports", "subject": "wrong target",
        }])


def test_reconcile_rejects_cross_project_historical_ir():
    source = build_historical_ir({**candidate(), "project_id": "other"})
    with pytest.raises(ValueError, match="project does not match"):
        reconcile_historical_irs(active(), [source], [])


def test_discovery_returns_metadata_without_raw_summaries(tmp_path):
    source = build_historical_ir(candidate())
    path = tmp_path / "historical-ir" / "agentos-core" / f"{source['historical_ir_id']}.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(source), encoding="utf-8")
    items = discover_historical_irs("agentos-core", data_root=tmp_path)
    assert items[0]["historical_ir_id"] == source["historical_ir_id"]
    assert items[0]["raw_conversation_copied"] is False
    assert "walkthrough.md" not in json.dumps(items)
