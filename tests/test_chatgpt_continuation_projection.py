from __future__ import annotations

import json

import pytest

from agent_core import chatgpt_continuation_projection as projection


def _active():
    # Canonical agentos.ir/v1 intentionally carries generation/goal state but not
    # project identity. Project authority lives in resolution.project.id.
    canonical_ir = {
        "schema_version": "agentos.ir/v1",
        "index_id": "idx-1",
        "ir_id": "ir-1",
        "goal": "Continue AgentOS Core",
        "constraints": [],
        "decisions": [],
        "pending_tasks": [],
        "continuation": {"next_action": "verify fresh ChatGPT hydration"},
    }
    return {
        "ok": True,
        "schema": "agentos.one-active-resolve/v1",
        "source": "ONE_ACTIVE_CONTINUATION",
        "selector": {"project_id": "agentos-core", "index_id": "idx-1", "ir_id": "ir-1"},
        "resolution": {
            "schema": "agentos.resolve-result/v1",
            "project": {"id": "agentos-core"},
            "execution_head": {"schema": "agentos.execution-head/v1", "index_id": "idx-1"},
            "continuation": {"canonical_ir": canonical_ir},
            "next_action": "verify fresh ChatGPT hydration",
        },
        "credential_exposed": False,
    }


def test_validate_active_requires_exact_generation_project_authority_and_credential_boundary():
    selector, resolution = projection._validate_active(_active())
    assert selector == {"project_id": "agentos-core", "index_id": "idx-1", "ir_id": "ir-1"}
    assert resolution["project"]["id"] == "agentos-core"
    assert "project_id" not in resolution["continuation"]["canonical_ir"]
    assert resolution["continuation"]["canonical_ir"]["goal"] == "Continue AgentOS Core"

    wrong_project = _active()
    wrong_project["resolution"]["project"]["id"] = "other-project"
    with pytest.raises(projection.ProjectionError, match="resolution_project_mismatch"):
        projection._validate_active(wrong_project)

    bad_ir = _active()
    bad_ir["resolution"]["continuation"]["canonical_ir"]["ir_id"] = "ir-other"
    with pytest.raises(projection.ProjectionError, match="canonical_ir_id_mismatch"):
        projection._validate_active(bad_ir)

    bad_index = _active()
    bad_index["resolution"]["continuation"]["canonical_ir"]["index_id"] = "idx-other"
    with pytest.raises(projection.ProjectionError, match="canonical_ir_index_mismatch"):
        projection._validate_active(bad_index)

    exposed = _active()
    exposed["credential_exposed"] = True
    with pytest.raises(projection.ProjectionError, match="credential_boundary_violation"):
        projection._validate_active(exposed)


def test_active_projection_uses_private_endpoint_and_keeps_full_canonical_ir(monkeypatch):
    calls = []

    def fake_request(method, url, *, token, payload=None):
        calls.append((method, url, token, payload))
        return 200, _active()

    monkeypatch.setattr(projection, "_json_request", fake_request)
    result = projection._active_projection("http://127.0.0.1:8780", "controller-secret")
    assert calls[0][1].endswith("/v1/controller/continuation/active")
    assert result["selector"]["ir_id"] == "ir-1"
    assert result["resolution"]["continuation"]["canonical_ir"]["goal"] == "Continue AgentOS Core"
    assert result["credential_exposed"] is False
    assert result["projection_sha256"].startswith("sha256:")


def test_publish_once_writes_only_fixed_private_target_and_public_result_is_identity_only(monkeypatch):
    active = _active()
    calls = []

    def fake_request(method, url, *, token, payload=None):
        calls.append((method, url, token, payload))
        if url.startswith("http://127.0.0.1"):
            return 200, active
        if method == "GET":
            return 404, None
        return 201, {"content": {"sha": "new-sha"}}

    monkeypatch.setattr(projection, "_json_request", fake_request)
    result = projection.publish_once(
        one_url="http://127.0.0.1:8780",
        controller_token="controller-secret",
        github_token="github-secret",
    )
    assert result["ok"] is True
    assert result["updated"] is True
    assert result["target"] == "alston-personal/my-agent-data:projects/agentos-core/continuity/chatgpt-active.json"
    rendered = json.dumps(result)
    assert "Continue AgentOS Core" not in rendered
    assert "controller-secret" not in rendered
    assert "github-secret" not in rendered

    put = next(call for call in calls if call[0] == "PUT")
    assert "/repos/alston-personal/my-agent-data/contents/projects/agentos-core/continuity/chatgpt-active.json" in put[1]
    assert put[3]["branch"] == "main"


def test_same_generation_is_noop_even_when_published_at_changes(monkeypatch):
    active = _active()
    requests = []

    def fake_request_first(method, url, *, token, payload=None):
        requests.append((method, url, payload))
        if url.startswith("http://127.0.0.1"):
            return 200, active
        raise AssertionError("unexpected GitHub call")

    monkeypatch.setattr(projection, "_json_request", fake_request_first)
    first = projection._active_projection("http://127.0.0.1:8780", "controller-secret")

    def fake_existing(_token):
        return "sha-existing", dict(first)

    monkeypatch.setattr(projection, "_existing_projection", fake_existing)
    result = projection.publish_once(
        one_url="http://127.0.0.1:8780",
        controller_token="controller-secret",
        github_token="github-secret",
    )
    assert result["updated"] is False
