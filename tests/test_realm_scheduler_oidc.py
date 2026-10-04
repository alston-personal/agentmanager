import time
from pathlib import Path

import pytest

from agent_core.realm_server import _validate_github_scheduler_claims


def _claims():
    now = int(time.time())
    return {
        "iss": "https://token.actions.githubusercontent.com",
        "aud": "agentos-scheduler",
        "repository": "alston-personal/agentmanager",
        "ref": "refs/heads/core/integration",
        "event_name": "push",
        "sha": "a" * 40,
        "workflow_ref": "alston-personal/agentmanager/.github/workflows/main-agent-executor-health-acceptance.yml@refs/heads/core/integration",
        "iat": now - 5,
        "nbf": now - 5,
        "exp": now + 300,
    }


def test_scheduler_oidc_claims_accept_canonical_integration_identity():
    _validate_github_scheduler_claims(_claims())


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("aud", "other"),
        ("repository", "other/repo"),
        ("ref", "refs/heads/main"),
        ("event_name", "pull_request"),
        ("sha", "not-a-sha"),
    ],
)
def test_scheduler_oidc_claims_fail_closed(key, value):
    claims = _claims()
    claims[key] = value
    with pytest.raises(PermissionError):
        _validate_github_scheduler_claims(claims)


def test_scheduler_routes_do_not_relax_other_controller_auth():
    text = Path("agent_core/realm_server.py").read_text(encoding="utf-8")
    assert "def _authorize_scheduler" in text
    assert "github oidc source commit mismatch" in text
    assert "if parsed.path == '/v1/controller/scheduler/submit':" in text
    # Runtime rollout remains on the long-lived controller credential.
    runtime = text.split("if parsed.path == '/v1/controller/runtime/rollout':", 1)[1][:300]
    assert "self._authorize_controller()" in runtime


def test_scheduler_oidc_claims_accept_default_branch_health_carrier_only():
    claims = _claims()
    claims["ref"] = "refs/heads/main"
    claims["event_name"] = "schedule"
    claims["workflow_ref"] = "alston-personal/agentmanager/.github/workflows/executor-health-reconcile-schedule.yml@refs/heads/main"
    _validate_github_scheduler_claims(claims)


def test_scheduler_oidc_claims_reject_other_default_branch_workflow():
    claims = _claims()
    claims["ref"] = "refs/heads/main"
    claims["event_name"] = "schedule"
    claims["workflow_ref"] = "alston-personal/agentmanager/.github/workflows/other.yml@refs/heads/main"
    with pytest.raises(PermissionError):
        _validate_github_scheduler_claims(claims)
