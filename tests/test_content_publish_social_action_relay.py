from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentos_node import action_relay
from agentos_node.action_relay import ActionRelayWorker
from agentos_node import content_publish_social_action_relay as social


@pytest.fixture(autouse=True)
def no_group_mutation(monkeypatch):
    monkeypatch.setattr(action_relay, "_share", lambda *args, **kwargs: None)


def config(tmp_path: Path) -> Path:
    path=tmp_path/"accounts-config.json"
    path.write_text(json.dumps({
        "schema":"agentos.content-publish-account-config/v1",
        "accounts":{
            "oursong_alstonhuang":{
                "platform":"threads",
                "product_id":"content-publish",
                "expected_username":"oursong_alstonhuang",
                "auth_profile":"persona",
                "bootstrap":{"kind":"legacy-zeus-writer-env","env_key":"SOC_THREADS_TOKEN"},
            }
        }
    }),encoding="utf-8")
    return path


def test_account_config_refuses_unknown_and_arbitrary_bootstrap(monkeypatch,tmp_path):
    monkeypatch.setattr(social,"ACCOUNT_CONFIG",config(tmp_path))
    with pytest.raises(ValueError):
        social._load_account_config("../etc")
    with pytest.raises(ValueError):
        social._load_account_config("unknown")


def test_bootstrap_never_accepts_token_or_path_params(monkeypatch,tmp_path):
    monkeypatch.setattr(social,"ACCOUNT_CONFIG",config(tmp_path))
    with pytest.raises(ValueError):
        social.bootstrap_account({"account_ref":"oursong_alstonhuang","token":"x"})
    with pytest.raises(ValueError):
        social.bootstrap_account({"account_ref":"oursong_alstonhuang","env_path":"/tmp/x"})


def test_missing_legacy_token_is_auth_required_and_secret_free(monkeypatch,tmp_path):
    monkeypatch.setattr(social,"ACCOUNT_CONFIG",config(tmp_path))
    monkeypatch.setattr(social,"LEGACY_ENV",tmp_path/"missing.env")
    result=social.bootstrap_account({"account_ref":"oursong_alstonhuang"})
    assert result["status"]=="AUTH_REQUIRED"
    assert result["credential_exposed"] is False
    assert result["side_effect"] is False


def test_inspect_requires_host_registry_and_does_not_expose_key(monkeypatch,tmp_path):
    monkeypatch.setattr(social,"ACCOUNT_CONFIG",config(tmp_path))
    monkeypatch.setattr(social,"ACCOUNT_REGISTRY",tmp_path/"registry.json")
    result=social.inspect_account({"account_ref":"oursong_alstonhuang"})
    assert result["status"]=="AUTH_REQUIRED"
    assert "key" not in json.dumps(result).lower()


def test_dispatcher_capsules_contain_only_account_ref(monkeypatch,tmp_path):
    monkeypatch.setattr(social,"ACCOUNT_CONFIG",config(tmp_path))
    monkeypatch.setattr(social,"LEGACY_ENV",tmp_path/"missing.env")
    root=tmp_path/"relay"
    dispatcher=social.ContentPublishSocialDispatcher(root)
    submitted=dispatcher.submit_bootstrap(account_ref="oursong_alstonhuang")
    capsule=json.loads((root/"inbox"/f"{submitted['task_id']}.json").read_text())
    assert capsule["action"]==social.BOOTSTRAP_ACTION
    assert capsule["params"]=={"account_ref":"oursong_alstonhuang"}
    assert capsule["authority"]["arbitrary_shell"] is False
    ActionRelayWorker(root).process_one()
    receipt=dispatcher.inspect(submitted["task_id"])
    assert receipt["status"]=="AUTH_REQUIRED"
    assert receipt["credential_exposed"] is False
    assert receipt["side_effect"] is False
