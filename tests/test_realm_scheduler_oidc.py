import time
from pathlib import Path

import pytest

from agent_core.realm_server import _validate_github_scheduler_claims, _validate_main_runtime_repair_intent, _validate_main_galaxy_intent, RealmRequestHandler


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


def test_scheduler_oidc_health_carrier_accepts_issue_comment_event():
    claims = _claims()
    claims["ref"] = "refs/heads/main"
    claims["event_name"] = "issue_comment"
    claims["workflow_ref"] = "alston-personal/agentmanager/.github/workflows/executor-health-reconcile-schedule.yml@refs/heads/main"
    _validate_github_scheduler_claims(claims)


def test_scheduler_oidc_canonical_workflow_rejects_issue_comment_event():
    claims = _claims()
    claims["event_name"] = "issue_comment"
    with pytest.raises(PermissionError):
        _validate_github_scheduler_claims(claims)


def test_scheduler_oidc_accepts_only_approved_main_vision_studio_push():
    claims = _claims()
    claims["ref"] = "refs/heads/main"
    claims["workflow_ref"] = "alston-personal/agentmanager/.github/workflows/vision-studio-rain-exit.yml@refs/heads/main"
    claims["event_name"] = "push"
    _validate_github_scheduler_claims(claims)


@pytest.mark.parametrize(
    ("ref", "workflow_ref", "event_name"),
    [
        ("refs/heads/main", "alston-personal/agentmanager/.github/workflows/vision-studio-rain-exit.yml@refs/heads/main", "pull_request"),
        ("refs/heads/main", "alston-personal/agentmanager/.github/workflows/vision-studio-rain-exit.yml@refs/heads/main", "workflow_dispatch"),
        ("refs/heads/main", "alston-personal/agentmanager/.github/workflows/another-video.yml@refs/heads/main", "push"),
        ("refs/heads/other", "alston-personal/agentmanager/.github/workflows/vision-studio-rain-exit.yml@refs/heads/main", "push"),
    ],
)
def test_scheduler_oidc_vision_studio_carrier_rejects_other_authority(ref, workflow_ref, event_name):
    claims = _claims()
    claims.update({"ref": ref, "workflow_ref": workflow_ref, "event_name": event_name})
    with pytest.raises(PermissionError):
        _validate_github_scheduler_claims(claims)


def test_only_signed_main_runtime_repair_workflow_can_get_scheduler_authority():
    claims = _claims()
    claims["ref"] = "refs/heads/main"
    claims["workflow_ref"] = ("alston-personal/agentmanager/.github/workflows/"
                              "main-action-runtime-migration-20261007.yml@refs/heads/main")
    claims["event_name"] = "push"
    _validate_github_scheduler_claims(claims)
    for changed in (
        {"workflow_ref": "alston-personal/agentmanager/.github/workflows/unrelated.yml@refs/heads/main"},
        {"event_name": "pull_request"},
        {"event_name": "workflow_dispatch"},
        {"ref": "refs/heads/some-branch"},
    ):
        with pytest.raises(PermissionError):
            _validate_github_scheduler_claims({**claims, **changed})


def test_main_repair_oidc_can_only_submit_exact_empty_payload():
    claims = _claims()
    claims.update(ref="refs/heads/main", event_name="push",
        workflow_ref=("alston-personal/agentmanager/.github/workflows/"
                      "main-action-runtime-migration-20261007.yml@refs/heads/main"))
    good = {
        "schema": "agentos.runner-window-dispatch/v1",
        "capability": "agentos.runtime",
        "operation": "repair",
        "source_commit": "a" * 40,
        "payload": {},
    }
    _validate_main_runtime_repair_intent(claims, good)
    candidates = [
        {**good, "operation": "restart"},
        {**good, "capability": "agentos.realm_gateway"},
        {**good, "source_commit": "b" * 40},
        {**good, "payload": {"script": "echo unsafe"}},
        {**good, "request_id": "arbitrary-receipt"},
        {**good, "credential": "secret"},
    ]
    for request in candidates:
        with pytest.raises(PermissionError):
            _validate_main_runtime_repair_intent(claims, request)



def test_main_runtime_oidc_cannot_call_generic_scheduler_controller_endpoints(monkeypatch):
    from types import SimpleNamespace
    claims = _claims()
    claims.update(ref="refs/heads/main", event_name="push",
        workflow_ref=("alston-personal/agentmanager/.github/workflows/"
                      "main-action-runtime-migration-20261007.yml@refs/heads/main"))
    monkeypatch.setattr("agent_core.realm_server._verify_github_scheduler_oidc", lambda _: claims)
    handler = object.__new__(RealmRequestHandler)
    handler.server = SimpleNamespace(controller_token="some-other-secret")
    handler._bearer = lambda: "signed-oidc-token"
    for method, path in (
        ("POST", "/v1/controller/scheduler/submit"),
        ("GET", "/v1/controller/scheduler"),
        ("GET", "/v1/controller/scheduler/requests/another-user-job"),
        ("GET", "/v1/dispatch/requests/agentos.transport.repair-1111111111-aaaaaaaa-extra"),
        ("GET", "/v1/dispatch/requests/agentos.vision_studio.produce-test123"),
        ("POST", "/v1/monitor"),
    ):
        handler.command = method
        handler.path = path
        with pytest.raises(PermissionError):
            handler._authorize_scheduler()
    for method, path in (
        ("GET", "/v1/dispatch"),
        ("POST", "/v1/dispatch"),
        ("GET", "/v1/dispatch/requests/agentos.transport.repair-1762967000-1234abcd"),
    ):
        handler.command = method
        handler.path = path
        assert handler._authorize_scheduler() is claims



def _galaxy_main_claims():
    claims = _claims()
    claims.update(
        ref="refs/heads/main",
        workflow_ref=(
            "alston-personal/agentmanager/.github/workflows/"
            "oracle-install-galaxy-threads-experiment-monitor.yml@refs/heads/main"
        ),
        event_name="workflow_dispatch",
    )
    return claims


def test_main_galaxy_oidc_accepts_only_exact_manual_workflow():
    claims = _galaxy_main_claims()
    _validate_github_scheduler_claims(claims)
    for changed in (
        {"event_name": "push"},
        {"event_name": "schedule"},
        {"event_name": "pull_request"},
        {"workflow_ref": "alston-personal/agentmanager/.github/workflows/other.yml@refs/heads/main"},
        {"ref": "refs/heads/core/integration"},
    ):
        altered = {**claims, **changed}
        if altered["ref"] == "refs/heads/core/integration":
            # This remains the legacy broad carrier; assert narrow predicate
            # does not mistake it for the new main-only Galaxy identity.
            from agent_core.realm_server import _is_main_galaxy_claims
            assert not _is_main_galaxy_claims(altered)
        else:
            with pytest.raises(PermissionError):
                _validate_github_scheduler_claims(altered)


def test_main_galaxy_oidc_can_only_dispatch_exact_migration():
    claims = _galaxy_main_claims()
    good = {
        "schema": "agentos.runner-window-dispatch/v1",
        "capability": "social.monitor",
        "operation": "runtime.migrate",
        "source_commit": "a" * 40,
        "payload": {},
    }
    _validate_main_galaxy_intent(claims, good)
    for changed in (
        {"operation": "run"},
        {"capability": "agentos.runtime"},
        {"source_commit": "b" * 40},
        {"payload": {"arbitrary": "argument"}},
        {"request_id": "unrelated"},
        {"shell": "true"},
    ):
        with pytest.raises(PermissionError):
            _validate_main_galaxy_intent(claims, {**good, **changed})


def test_main_galaxy_oidc_can_only_access_catalog_dispatch_and_own_receipts(monkeypatch):
    from types import SimpleNamespace
    claims = _galaxy_main_claims()
    monkeypatch.setattr("agent_core.realm_server._verify_github_scheduler_oidc", lambda _: claims)
    handler = object.__new__(RealmRequestHandler)
    handler.server = SimpleNamespace(controller_token="different-controller-secret")
    handler._bearer = lambda: "signed-galaxy-oidc"
    for method, path in (
        ("POST", "/v1/controller/scheduler/submit"),
        ("GET", "/v1/controller/scheduler"),
        ("GET", "/v1/controller/scheduler/requests/other"),
        ("GET", "/v1/dispatch/requests/agentos.vision_studio.produce-test"),
        ("GET", "/v1/dispatch/requests/agentos.social_threads_experiment_monitor.migrate_runtime-X/invalid"),
        ("POST", "/v1/monitor"),
    ):
        handler.command, handler.path = method, path
        with pytest.raises(PermissionError):
            handler._authorize_scheduler()
    for method, path in (
        ("GET", "/v1/dispatch"),
        ("POST", "/v1/dispatch"),
        ("GET", "/v1/dispatch/requests/agentos.social_threads_experiment_monitor.migrate_runtime-example"),
    ):
        handler.command, handler.path = method, path
        assert handler._authorize_scheduler() is claims
