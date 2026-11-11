"""Executor job dispatch must reject stale code tasks before Node transport."""
from __future__ import annotations

import pytest

from agent_core.controller_service import ControllerService
from agent_core.executor_job_contract import JOB_TYPES, EXECUTOR_JOB_SCHEMA
from tests.test_executor_job_controller_route import FakeDispatcher, _fabric


def request():
    spec = JOB_TYPES["engineering.realm-device-flow.fix"]
    return {
        "schema": EXECUTOR_JOB_SCHEMA,
        "job_type": spec.job_type,
        "project_id": spec.project_id,
        "executor_class": spec.executor_class,
        "workload_ref": spec.workload_ref,
        "authority": spec.authority,
    }


def dispatch(controller):
    return controller.dispatch({
        "schema": "agentos.controller-dispatch/v0.1",
        "node_id": "oracle-core-node",
        "action": "agentos.executor.job",
        "payload": request(),
    })


def verdict(status, allowed=False):
    return {
        "schema": "agentos.branch-resume-gate/v1",
        "status": status,
        "allowed": allowed,
        "production_authorized": False,
        "main_sha": "a" * 40,
        "merge_base_sha": "a" * 40,
        "work_sha": "b" * 40,
    }


def test_code_job_missing_freshness_probe_fails_closed(tmp_path):
    worker = FakeDispatcher()
    controller = ControllerService(_fabric(tmp_path), executor_job_dispatcher=worker)
    with pytest.raises(ValueError, match="CODE_MAINLINE_PROBE_UNAVAILABLE"):
        dispatch(controller)
    assert not worker.calls


def test_stale_or_untrusted_verdict_cannot_enqueue_code_job(tmp_path):
    for result in (None, {}, verdict("RECONCILE_REQUIRED"),
                   verdict("READ_ONLY_INSPECT", True),
                   {**verdict("MAINLINE_CURRENT", True), "production_authorized": True},
                   {**verdict("MAINLINE_CURRENT", True), "allowed": "true"},
                   {**verdict("MAINLINE_CURRENT", True), "merge_base_sha": "c" * 40},
                   {**verdict("MAINLINE_CURRENT", True), "work_sha": "not-pinned"}):
        worker = FakeDispatcher()
        controller = ControllerService(
            _fabric(tmp_path),
            executor_job_dispatcher=worker,
            code_resume_probe=lambda _, value=result: value,
        )
        with pytest.raises(ValueError, match="CODE_MAINLINE_RECONCILE_REQUIRED"):
            dispatch(controller)
        assert not worker.calls


def test_fresh_pinned_verdict_allows_code_dispatch(tmp_path):
    seen = []
    worker = FakeDispatcher()
    controller = ControllerService(
        _fabric(tmp_path),
        executor_job_dispatcher=worker,
        code_resume_probe=lambda spec: (seen.append(spec.job_type) or verdict("MAINLINE_CURRENT", True)),
    )
    result = dispatch(controller)
    assert result["job_id"] == "action-12345678"
    assert seen == ["engineering.realm-device-flow.fix"]
    assert len(worker.calls) == 1


def test_probe_errors_fail_closed_without_leaking_provider_details(tmp_path):
    worker = FakeDispatcher()
    def exploding_probe(_):
        raise RuntimeError("internal api token must not appear")
    controller = ControllerService(
        _fabric(tmp_path), executor_job_dispatcher=worker,
        code_resume_probe=exploding_probe,
    )
    with pytest.raises(ValueError, match="CODE_MAINLINE_EVIDENCE_UNAVAILABLE") as err:
        dispatch(controller)
    assert "internal api token" not in str(err.value)
    assert not worker.calls


def test_read_only_executor_unchanged_without_code_probe(tmp_path):
    from agent_core.executor_job_contract import canonical_experience_regression_request
    worker = FakeDispatcher()
    controller = ControllerService(_fabric(tmp_path), executor_job_dispatcher=worker)
    result = controller.dispatch({
        "schema": "agentos.controller-dispatch/v0.1",
        "node_id": "oracle-core-node",
        "action": "agentos.executor.job",
        "payload": canonical_experience_regression_request(),
    })
    assert result["job_id"] == "action-12345678"
    assert len(worker.calls) == 1
