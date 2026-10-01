from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentos_node import action_relay
from agentos_node.action_relay import ActionRelayWorker
from agentos_node.content_publish_action_relay import (
    ACTION,
    CAPABILITY,
    ContentPublishXAuthDispatcher,
    inspect_legacy_x_auth,
)
from runtime_core.x_auth_probe import CREDENTIAL_KEYS, inspect_x_auth


class Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


@pytest.fixture(autouse=True)
def no_group_mutation(monkeypatch):
    monkeypatch.setattr(action_relay, "_share", lambda *args, **kwargs: None)


def creds():
    return {name: "secret-" + name.lower() for name in CREDENTIAL_KEYS}


def test_identity_success_does_not_overclaim_publish_entitlement():
    result = inspect_x_auth(
        creds(),
        expected_username="oursong_alston",
        opener=lambda req, timeout: Response(
            {"data": {"id": "123", "username": "oursong_alston"}}
        ),
    )
    assert result["authentication_success"] is True
    assert result["authentication_status"] == "READY"
    assert result["status"] == "UNKNOWN"
    assert result["write_entitlement"] == "UNKNOWN"
    assert result["media_entitlement"] == "UNKNOWN"
    assert result["credential_exposed"] is False
    assert result["side_effect"] is False


def test_missing_credentials_is_auth_required_without_values():
    result = inspect_x_auth({})
    assert result["status"] == "AUTH_REQUIRED"
    assert result["authentication_success"] is False
    assert set(result["credential_presence"]) == set(CREDENTIAL_KEYS)
    assert not any(result["credential_presence"].values())
    encoded = json.dumps(result)
    assert "secret-" not in encoded


def test_legacy_env_loader_projects_presence_not_secret_values(tmp_path: Path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text(
        "\n".join(
            [
                "X_API_KEY=key-value",
                "X_API_SECRET='secret-value'",
                'X_ACCESS_TOKEN="token-value"',
                "X_ACCESS_SECRET=access-secret-value",
                "UNRELATED=do-not-read",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    def fake_probe(credentials, expected_username=""):
        assert expected_username == "oursong_alston"
        assert credentials["X_API_KEY"] == "key-value"
        return {
            "status": "UNKNOWN",
            "authentication_status": "READY",
            "authentication_success": True,
            "credential_presence": {name: True for name in CREDENTIAL_KEYS},
            "write_entitlement": "UNKNOWN",
            "media_entitlement": "UNKNOWN",
            "account_identity": {"id": "123", "username": "oursong_alston"},
            "reason": "identity only",
        }

    monkeypatch.setattr(
        "agentos_node.content_publish_action_relay.inspect_x_auth", fake_probe
    )
    result = inspect_legacy_x_auth(
        {"expected_username": "oursong_alston"}, env_path=env
    )
    encoded = json.dumps(result)
    assert result["credential_source"] == "legacy-zeus-writer-node-local"
    assert result["credential_exposed"] is False
    assert "key-value" not in encoded
    assert "secret-value" not in encoded
    assert result["account_identity"]["username"] == "oursong_alston"


def test_action_contract_rejects_caller_paths_tokens_and_extra_fields(tmp_path: Path):
    with pytest.raises(ValueError):
        inspect_legacy_x_auth({"env_path": str(tmp_path / ".env")})
    with pytest.raises(ValueError):
        inspect_legacy_x_auth({"token": "x"})
    with pytest.raises(ValueError):
        inspect_legacy_x_auth({"expected_username": "../bad"})


def test_dispatcher_uses_fixed_action_and_worker_receipt(monkeypatch, tmp_path: Path):
    env = tmp_path / ".env"
    env.write_text(
        "\n".join(f"{name}=value" for name in CREDENTIAL_KEYS) + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "agentos_node.content_publish_action_relay.LEGACY_ENV", env
    )

    def fake_probe(credentials, expected_username=""):
        return {
            "status": "UNKNOWN",
            "authentication_status": "READY",
            "authentication_success": True,
            "credential_presence": {name: True for name in CREDENTIAL_KEYS},
            "write_entitlement": "UNKNOWN",
            "media_entitlement": "UNKNOWN",
            "account_identity": {"id": "123", "username": expected_username},
            "reason": "identity only",
        }

    monkeypatch.setattr(
        "agentos_node.content_publish_action_relay.inspect_x_auth", fake_probe
    )

    root = tmp_path / "relay"
    dispatcher = ContentPublishXAuthDispatcher(root)
    submitted = dispatcher.submit(expected_username="oursong_alston")
    task_id = submitted["task_id"]
    capsule = json.loads((root / "inbox" / f"{task_id}.json").read_text())
    assert capsule["action"] == ACTION
    assert capsule["authority"]["arbitrary_shell"] is False
    assert set(capsule["params"]) == {"expected_username"}

    receipt = ActionRelayWorker(root).process_one()
    assert receipt is not None
    assert receipt["action"] == ACTION
    projected = dispatcher.inspect(task_id)
    assert projected is not None
    assert projected["action"] == CAPABILITY
    assert projected["authentication_success"] is True
    assert projected["credential_exposed"] is False
    assert projected["side_effect"] is False
