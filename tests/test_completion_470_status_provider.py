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
        "hidden": {"status": "waiting_external", "wake_condition": {"kind": "time", "not_before": "2030-01-01T00:00:00+00:00"}},
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


def test_one_receipt_roundtrip_preserves_bounded_status(tmp_path, monkeypatch):
    state = tmp_path / "work-items.json"
    state.write_text(json.dumps({"items": {
        p.TARGET: {"status": "waiting_external", "owner": "role://completion.controller",
                   "owner_generation": 284, "next_action": "PRIVATE ACTION",
                   "wake_condition": {"kind": "time", "not_before": "2030-01-01T00:00:00+00:00"}},
        "blocked": {"status": "blocked", "workspace": "/private/path"},
    }}), encoding="utf-8")
    monkeypatch.setattr(p, "STATE", state)
    req = canonical_executor_job_request(p.JOB_TYPE)
    result = _sanitize_provider_result(p.inspect_completion_470(req))
    receipt = project_executor_job_receipt(
        job_id="action_470_status_probe",
        request=req,
        executor_available=True,
        routable=True,
        authorized=True,
        successful=result["verdict"] == "PASS",
        result=result,
    )
    assert receipt["completion_status"] == "waiting_external"
    assert receipt["completion_owner_generation"] == 284
    assert receipt["completion_blocked_count"] == 1
    assert receipt["completion_waiting_count"] == 1
    assert receipt["completion_target_verified"] is False
    serialized = json.dumps(receipt)
    assert "PRIVATE ACTION" not in serialized
    assert "/private/path" not in serialized


def test_wait_due_time_preserved_and_private_reason_not_exposed(tmp_path, monkeypatch):
    from datetime import datetime, timedelta, timezone
    not_before = (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat()
    state = tmp_path / "work-items.json"
    state.write_text(json.dumps({"items": {p.TARGET: {
        "status": "waiting_external", "owner": "role://completion.controller",
        "wake_condition": {"kind": "time", "not_before": not_before},
        "blocker": "private operator token value",
    }}}))
    monkeypatch.setattr(p, "STATE", state)
    req = canonical_executor_job_request(p.JOB_TYPE)
    result = _sanitize_provider_result(p.inspect_completion_470(req))
    receipt = project_executor_job_receipt(
        job_id="action_470_wake_test", request=req, executor_available=True,
        routable=True, authorized=True, successful=True, result=result,
    )
    assert receipt["completion_wake_not_before"] == not_before
    assert receipt["completion_wake_overdue"] is True
    assert receipt["completion_wait_reason_category"] == "present"
    assert "private operator token value" not in json.dumps(receipt)


def test_invalid_wait_condition_fails_closed(tmp_path, monkeypatch):
    state = tmp_path / "work-items.json"
    state.write_text(json.dumps({"items": {p.TARGET: {
        "status": "waiting_external", "owner": "role://completion.controller",
    }}}))
    monkeypatch.setattr(p, "STATE", state)
    result = p.inspect_completion_470(canonical_executor_job_request(p.JOB_TYPE))
    assert result["verdict"] == "FAIL"


def test_history_counters_bounded_without_raw_event_leak(tmp_path, monkeypatch):
    state = tmp_path / "work-items.json"
    state.write_text(json.dumps({"items": {p.TARGET: {
        "status": "waiting_external",
        "wake_condition": {"kind": "time", "not_before": "2030-01-01T00:00:00+00:00"},
        "history": [
            {"event": "stale_reclaim", "private": "secret-row"},
            {"event": "wake", "reason": "private-user-data"},
            {"event": "wait_external", "reason": "private-provider"},
        ]
    }}}))
    monkeypatch.setattr(p, "STATE", state)
    req = canonical_executor_job_request(p.JOB_TYPE)
    result = _sanitize_provider_result(p.inspect_completion_470(req))
    receipt = project_executor_job_receipt(
        job_id="action_470_history_probe", request=req,
        executor_available=True, routable=True, authorized=True,
        successful=True, result=result,
    )
    assert receipt["completion_last_event_category"] == "wait_external"
    assert receipt["completion_recent_wake_count"] == 1
    assert receipt["completion_recent_reclaim_count"] == 1
    assert receipt["completion_target_reclaimed"] is True
    assert "private" not in json.dumps(receipt)
    assert "secret-row" not in json.dumps(receipt)


def test_ancient_reclaim_not_treated_as_recent(tmp_path, monkeypatch):
    state = tmp_path / "work-items.json"
    history = [{"event": "stale_reclaim"}] + [{"event": "heartbeat"} for _ in range(100)]
    state.write_text(json.dumps({"items": {p.TARGET: {
        "status": "waiting_external",
        "wake_condition": {"kind": "time", "not_before": "2030-01-01T00:00:00+00:00"},
        "history": history,
    }}}))
    monkeypatch.setattr(p, "STATE", state)
    result = p.inspect_completion_470(canonical_executor_job_request(p.JOB_TYPE))
    assert result["completion_recent_reclaim_count"] == 0
    assert result["completion_target_reclaimed"] is False


def test_machine_blocker_is_bounded_and_private(tmp_path, monkeypatch):
    state = tmp_path / "work-items.json"
    state.write_text(json.dumps({"items": {p.TARGET: {
        "status": "waiting_external",
        "wake_condition": {"kind": "time", "not_before": "2030-01-01T00:00:00+00:00"},
        "last_blocker_kind": "RUNTIME_HEALTH",
        "machine_retry_count": 18,
        "blocker": "SECRET_TOKEN_NOT_FOR_RECEIPT",
    }}}))
    monkeypatch.setattr(p, "STATE", state)
    req = canonical_executor_job_request(p.JOB_TYPE)
    safe = _sanitize_provider_result(p.inspect_completion_470(req))
    receipt = project_executor_job_receipt(
        job_id="action_470_blocker_probe", request=req,
        executor_available=True, routable=True, authorized=True, successful=True,
        result=safe)
    assert receipt["completion_machine_blocker_kind"] == "RUNTIME_HEALTH"
    assert receipt["completion_machine_retry_count"] == 18
    assert "SECRET_TOKEN_NOT_FOR_RECEIPT" not in json.dumps(receipt)


def test_unapproved_blocker_kind_is_reduced_to_unknown(tmp_path, monkeypatch):
    state = tmp_path / "work-items.json"
    state.write_text(json.dumps({"items": {p.TARGET: {
        "status": "waiting_external",
        "wake_condition": {"kind": "time", "not_before": "2030-01-01T00:00:00+00:00"},
        "last_blocker_kind": "SECRET_INVALID",
    }}}))
    monkeypatch.setattr(p, "STATE", state)
    result = p.inspect_completion_470(canonical_executor_job_request(p.JOB_TYPE))
    assert result["completion_machine_blocker_kind"] == "UNKNOWN"
