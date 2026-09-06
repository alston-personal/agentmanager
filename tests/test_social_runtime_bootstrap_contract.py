from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from agentos_node import bootstrap_control as bc


SHA = "a" * 40
ROOT = Path(__file__).resolve().parents[1]
SYSTEM_DEPLOY = ROOT / "scripts" / "deploy_social_runtime_system.sh"


def _payload(*, params: dict | None = None, authority: dict | None = None) -> dict:
    return {
        "schema": bc.SCHEMA,
        "request_id": "social-test",
        "action": bc.ACTION_DEPLOY_SOCIAL_RUNTIME,
        "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "params": {"source_commit": SHA} if params is None else params,
        "authority": authority
        or {"source": "github-actions", "target_user": "ubuntu", "arbitrary_shell": False},
    }


def _owned_request(tmp_path, monkeypatch):
    path = tmp_path / "social-test.request.json"
    path.write_text("{}\n", encoding="utf-8")
    os.chmod(path, 0o600)
    monkeypatch.setattr(bc.pwd, "getpwuid", lambda _uid: SimpleNamespace(pw_name="agentos-node"))
    return path


def test_social_runtime_action_is_explicitly_allowlisted():
    assert bc.ACTION_DEPLOY_SOCIAL_RUNTIME == "agentos.social_runtime.deploy"
    assert bc.ACTION_DEPLOY_SOCIAL_RUNTIME in bc.ALLOWED_ACTIONS


def test_social_runtime_action_requires_exact_source_commit(tmp_path, monkeypatch):
    path = _owned_request(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="requires exact source_commit"):
        bc._validate_request(path, _payload(params={}))
    with pytest.raises(ValueError, match="40-hex"):
        bc._validate_request(path, _payload(params={"source_commit": "main"}))


def test_social_runtime_action_rejects_caller_selected_execution_fields(tmp_path, monkeypatch):
    path = _owned_request(tmp_path, monkeypatch)
    for forbidden in ("script", "path", "argv", "env", "user", "unit", "command"):
        with pytest.raises(ValueError, match="unsupported bootstrap params"):
            bc._validate_request(path, _payload(params={"source_commit": SHA, forbidden: "x"}))


def test_social_runtime_action_requires_bounded_authority(tmp_path, monkeypatch):
    path = _owned_request(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="invalid authority envelope"):
        bc._validate_request(
            path,
            _payload(authority={"source": "github-actions", "target_user": "agentos-node", "arbitrary_shell": False}),
        )
    with pytest.raises(ValueError, match="arbitrary shell is forbidden"):
        bc._validate_request(
            path,
            _payload(authority={"source": "github-actions", "target_user": "ubuntu", "arbitrary_shell": True}),
        )


def test_social_runtime_execute_uses_only_fixed_canonical_script(monkeypatch):
    calls = []

    def fake(script_rel, *, timeout, source_commit=None, env_extra=None):
        calls.append((script_rel, timeout, source_commit, env_extra))
        return {"ok": True, "source_commit": source_commit}

    monkeypatch.setattr(bc, "_run_canonical_script", fake)
    result = bc._execute(bc.ACTION_DEPLOY_SOCIAL_RUNTIME, SHA)
    assert result == {"ok": True, "source_commit": SHA}
    assert calls == [("scripts/deploy_social_runtime_system.sh", 180, SHA, None)]


def test_system_deploy_is_fixed_to_agentos_node_and_system_scope():
    text = SYSTEM_DEPLOY.read_text(encoding="utf-8")
    assert 'SERVICE_USER="agentos-node"' in text
    assert 'SERVICE_NAME="agentos-social-runtime.service"' in text
    assert 'UNIT_FILE="/etc/systemd/system/$SERVICE_NAME"' in text
    assert "User=agentos-node" in text
    assert "WantedBy=multi-user.target" in text
    assert "systemctl --user" not in text
    assert "loginctl enable-linger" not in text
    assert "sudoers" in text
    assert "social_runtime_sudoers_mutation=NONE" in text


def test_system_deploy_fences_runtime_generation_to_core_integration():
    text = SYSTEM_DEPLOY.read_text(encoding="utf-8")
    assert 'CANONICAL_REF="core/integration"' in text
    assert 'git -C "$REPO" fetch --no-tags origin "$CANONICAL_REF"' in text
    assert 'if [ "$CANONICAL_HEAD" != "$SOURCE_COMMIT" ]' in text
    assert "social_runtime_deploy=NON_CANONICAL_SOURCE" in text


def test_system_deploy_does_not_embed_provider_credential_values():
    text = SYSTEM_DEPLOY.read_text(encoding="utf-8")
    assert "AGENTOS_THREADS_APP_ID=\n" in text
    assert "AGENTOS_THREADS_APP_SECRET=\n" in text
    assert "AGENTOS_SOCIAL_CONTROL_TOKEN=\n" in text
    assert "AGENTOS_SOCIAL_PRODUCTS_JSON={}\n" in text
