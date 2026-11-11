from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from agent_core.executor_job_contract import (
    ExecutorJobContractError,
    canonical_executor_job_request,
    validate_executor_job,
)
from agentos_node import colab_h3_smoke_provider as h3
from agentos_node.action_relay import _github_actions_dispatch
from agentos_node.executor_job_action_relay import COLAB_H3_SMOKE_PROVIDER_REGISTERED
from agentos_node.executor_job_adapter import DEFAULT_PROVIDERS


def _stamp(delta_minutes=0):
    return (datetime.now(timezone.utc) + timedelta(minutes=delta_minutes)).isoformat()


def _listed(items):
    return {"returncode": 0, "stdout": json.dumps(items), "stderr": ""}


def _recent_run(*, status="in_progress", conclusion="", run_id=44002):
    return {
        "databaseId": run_id,
        "createdAt": _stamp(-2),
        "headSha": "a" * 40,
        "status": status,
        "conclusion": conclusion,
        "url": "https://github.com/alston-personal/agentmanager/actions/runs/" + str(run_id),
    }


def test_smoke_job_is_fixed_semantic_contract_without_shell_authority():
    request = canonical_executor_job_request(h3.JOB_TYPE)
    spec = validate_executor_job(request)
    assert spec.workload_ref == "issue://3"
    assert spec.read_only is False
    assert COLAB_H3_SMOKE_PROVIDER_REGISTERED
    assert DEFAULT_PROVIDERS.get(h3.JOB_TYPE) is not None
    for name, value in [
        ("workflow", "oracle-deploy-anything.yml"),
        ("repository", "evil/repo"),
        ("ref", "main"),
        ("argv", ["bash", "-c", "curl"]),
        ("env", {"TOKEN": "no"}),
    ]:
        with pytest.raises(ExecutorJobContractError):
            validate_executor_job({**request, name: value})


@pytest.mark.parametrize("status,conclusion,classification", [
    ("queued", "", "COLAB_SMOKE_EXISTING_RUN_ACTIVE"),
    ("in_progress", "", "COLAB_SMOKE_EXISTING_RUN_ACTIVE"),
    ("completed", "success", "COLAB_SMOKE_ACTIONS_SUCCESS_NEEDS_RECEIPT"),
    ("completed", "failure", "COLAB_SMOKE_EXISTING_RUN_FAILED_NEEDS_TRIAGE"),
])
def test_recent_manual_run_blocks_duplicate_billable_dispatch(monkeypatch, status, conclusion, classification):
    calls = []
    monkeypatch.setattr(h3.action_relay, "_run", lambda *args, **kwargs: calls.append(args) or _listed([
        _recent_run(status=status, conclusion=conclusion),
    ]))
    monkeypatch.setattr(h3.action_relay, "_github_actions_dispatch",
                        lambda *args, **kwargs: pytest.fail("must not dispatch same recent smoke"))
    result = h3.run_h3_smoke(canonical_executor_job_request(h3.JOB_TYPE))
    assert len(calls) == 1
    assert result["classification"] == classification
    assert result["work_id"] == "gh-actions-run-44002"
    assert result["successful"] is False
    assert result["credential_exposed"] is False


def test_cannot_dispatch_when_run_discovery_fails(monkeypatch):
    monkeypatch.setattr(h3.action_relay, "_run",
                        lambda *args, **kwargs: {"returncode": 1, "stdout": "", "stderr": "403"})
    monkeypatch.setattr(h3.action_relay, "_github_actions_dispatch",
                        lambda *args, **kwargs: pytest.fail("unsafe if history unknown"))
    result = h3.run_h3_smoke(canonical_executor_job_request(h3.JOB_TYPE))
    assert result["classification"] == "COLAB_SMOKE_RUN_DISCOVERY_UNAVAILABLE"
    assert result["routable"] is False


def test_absent_recent_run_dispatches_one_fixed_workflow(monkeypatch):
    seen = []
    def stale_run(args, **kwargs):
        if args[1:3] == ["run", "list"]:
            older = _recent_run(status="completed", conclusion="failure")
            older["createdAt"] = _stamp(-1500)
            return _listed([older])
        return {"returncode": 0, "stdout": "a" * 40 + "\n", "stderr": ""}
    monkeypatch.setattr(h3.action_relay, "_run", stale_run)
    monkeypatch.setattr(h3.action_relay, "_github_actions_dispatch",
                        lambda params: seen.append(params) or {"ok": True, "run_id": 99003})
    out = h3.run_h3_smoke(canonical_executor_job_request(h3.JOB_TYPE))
    assert out["classification"] == "COLAB_SMOKE_DISPATCH_ACK_ONLY"
    assert out["work_id"] == "gh-actions-run-99003"
    assert out["verdict"] == "PENDING_RECEIPT"
    assert out["successful"] is False
    assert seen == [{
        "repository": "alston-personal/agentmanager",
        "workflow": "oracle-colab-minimax-h3-smoke.yml",
        "ref": "main",
        "expected_head_sha": "a" * 40,
        "inputs": {},
    }]


def test_action_relay_never_allows_parameters_for_h3_smoke():
    params = {
        "repository": "alston-personal/agentmanager",
        "workflow": "oracle-colab-minimax-h3-smoke.yml",
        "ref": "main",
        "expected_head_sha": "a" * 40,
        "inputs": {"gpu": "H100"},
    }
    with pytest.raises(ValueError, match="does not accept caller inputs"):
        _github_actions_dispatch(params)
    with pytest.raises(ValueError, match="not allowlisted"):
        _github_actions_dispatch({**params, "ref": "core/integration", "inputs": {}})
