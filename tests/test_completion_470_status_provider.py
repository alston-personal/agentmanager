from __future__ import annotations
import json

from agent_core.executor_job_contract import canonical_executor_job_request, project_executor_job_receipt
from agentos_node import completion_470_status_provider as p
from agentos_node.executor_job_adapter import ExecutorJobProviderRegistry, _sanitize_provider_result


def test_fixed_scope_ledger_projection(tmp_path, monkeypatch):
    state = tmp_path / "work-items.json"
    state.write_text(json.dumps({"items": {
        p.TARGET: {"status": "blocked", "owner": "role://lobster", "owner_generation": 283,
                   "next_action": "SECRET", "history": []},
        "hidden": {"status": "waiting_external"},
        "stale": {"status": "in_progress", "history": [{"event": "stale_reclaim"}]},
        "done": {"status": "done", "verification": {"status": "passed"}},
    }}), encoding="utf-8")
    monkeypatch.setattr(p, "STATE", state)
    req = canonical_executor_job_request("completion.470.status.inspect")
    result = p.inspect_completion_470(req)
    assert result["verdict"] == "PASS"
    assert result["completion_status"] == "blocked"
    assert result["completion_owner_generation"] == 283
    assert result["completion_active_count"] == 3
    assert result["completion_blocked_count"] == 1
    assert result["completion_waiting_count"] == 1
    assert result["completion_unreconciled_count"] == 1
    assert result["completion_target_verified"] is False
    safe = _sanitize_provider_result(result)
    assert "next_action" not in safe
    assert safe["completion_blocked_count"] == 1


def test_done_requires_verification(tmp_path, monkeypatch):
    state = tmp_path / "work-items.json"
    state.write_text(json.dumps({"items": {p.TARGET: {"status": "done", "verification": {"status": "passed"}}}}))
    monkeypatch.setattr(p, "STATE", state)
    result = p.inspect_completion_470(canonical_executor_job_request(p.JOB_TYPE))
    assert result["completion_target_verified"] is True


def test_corrupt_ledger_fails_closed(tmp_path, monkeypatch):
    state = tmp_path / "work-items.json"
    state.write_text("not-json")
    monkeypatch.setattr(p, "STATE", state)
    result = p.inspect_completion_470(canonical_executor_job_request(p.JOB_TYPE))
    assert result["verdict"] == "FAIL"
    assert result["successful"] is False


def test_provider_registration():
    registry = ExecutorJobProviderRegistry()
    assert p.register_completion_470_status_provider(registry)
    assert registry.get(p.JOB_TYPE).provider_id == p.PROVIDER_ID
