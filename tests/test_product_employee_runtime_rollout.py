from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.rollout_product_employee_runtime import build_request, rollout


SHA = "a" * 40


class FakeDispatcher:
    def __init__(self, receipt):
        self.receipt = receipt
        self.request = None
        self.task_id = "action-test-1"

    def submit(self, *, request):
        self.request = dict(request)
        return {
            "schema": "agentos.runtime-converge-submission/v1",
            "ok": True,
            "task_id": self.task_id,
            "state": "queued",
        }

    def inspect(self, task_id):
        assert task_id == self.task_id
        return dict(self.receipt)


def _env(**changes):
    value = {
        "GITHUB_REPOSITORY": "alston-personal/agentmanager",
        "GITHUB_REF": "refs/heads/core/integration",
        "GITHUB_SHA": SHA,
    }
    value.update(changes)
    return value


def _receipt(**changes):
    value = {
        "schema": "agentos.runtime-converge-receipt/v1",
        "ok": True,
        "action": "node.runtime.converge",
        "task_id": "action-test-1",
        "request_id": f"product-employee-rollout-{SHA}",
        "node_id": "oracle-core-node",
        "repository": "alston-personal/agentmanager",
        "source_ref": "core/integration",
        "source_commit": SHA,
        "previous_commit": "b" * 40,
        "resulting_commit": SHA,
        "health": "passed",
        "rollback": "not_needed",
        "status": "completed",
        "classification": "CONVERGED",
        "idempotent": False,
        "credential_exposed": False,
    }
    value.update(changes)
    return value


def test_build_request_is_fixed_to_current_core_integration_sha():
    request = build_request(_env())
    assert request == {
        "schema": "agentos.runtime-converge-request/v1",
        "request_id": f"product-employee-rollout-{SHA}",
        "node_id": "oracle-core-node",
        "repository": "alston-personal/agentmanager",
        "source_ref": "core/integration",
        "source_commit": SHA,
    }


@pytest.mark.parametrize(
    "changes",
    [
        {"GITHUB_REPOSITORY": "other/repo"},
        {"GITHUB_REF": "refs/heads/main"},
        {"GITHUB_SHA": "main"},
    ],
)
def test_rollout_source_cannot_be_selected_by_caller(changes):
    with pytest.raises(RuntimeError):
        build_request(_env(**changes))


def test_rollout_accepts_only_exact_healthy_sanitized_receipt():
    dispatcher = FakeDispatcher(_receipt())
    result = rollout(_env(), dispatcher=dispatcher, timeout_seconds=1, poll_seconds=0.01)
    assert result["resulting_commit"] == SHA
    assert result["health"] == "passed"
    assert result["credential_exposed"] is False
    assert dispatcher.request["source_commit"] == SHA


@pytest.mark.parametrize(
    "changes",
    [
        {"status": "failed", "ok": False, "classification": "tracked_checkout_dirty"},
        {"credential_exposed": True},
        {"resulting_commit": "c" * 40},
        {"health": "failed"},
    ],
)
def test_rollout_fails_closed_on_untrusted_receipt(changes):
    dispatcher = FakeDispatcher(_receipt(**changes))
    with pytest.raises(RuntimeError):
        rollout(_env(), dispatcher=dispatcher, timeout_seconds=1, poll_seconds=0.01)


def test_workflow_is_push_only_and_has_no_runtime_inputs():
    text = Path(".github/workflows/product-employee-runtime-rollout.yml").read_text(encoding="utf-8")
    assert "workflow_dispatch" not in text
    assert "inputs:" not in text
    assert "core/integration" in text
    assert "scripts/rollout_product_employee_runtime.py" in text
    assert "-m scripts.rollout_product_employee_runtime" in text
    assert "PYTHONPATH='$GITHUB_WORKSPACE'" in text
    assert "node.runtime.converge" not in text
