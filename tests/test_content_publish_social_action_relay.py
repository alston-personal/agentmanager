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
    assert result["public_publish_performed"] is False
    assert result["credential_migrated"] is False


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
    assert receipt["public_publish_performed"] is False
    assert receipt["credential_migrated"] is False


def test_successful_bootstrap_moves_token_only_into_vault(monkeypatch,tmp_path):
    monkeypatch.setattr(social,"ACCOUNT_CONFIG",config(tmp_path))
    legacy=tmp_path/"legacy.env"
    legacy.write_text("SOC_THREADS_TOKEN=super-secret-token\n",encoding="utf-8")
    monkeypatch.setattr(social,"LEGACY_ENV",legacy)
    monkeypatch.setattr(social,"SOCIAL_ENV",tmp_path/"social.env")
    monkeypatch.setattr(social,"SOCIAL_PRODUCT_DIR",tmp_path/"products")
    monkeypatch.setattr(social,"ACCOUNT_REGISTRY",tmp_path/"accounts.json")
    monkeypatch.setattr(
        social,
        "_threads_transport",
        lambda env: type("Transport",(),{
            "identity":lambda self,token: (
                {"id":"123","username":"oursong_alstonhuang"}
                if token=="super-secret-token" else (_ for _ in ()).throw(AssertionError(token))
            )
        })(),
    )
    monkeypatch.setattr(social,"register_product",lambda *a,**k:(True,tmp_path/"product.env"))
    monkeypatch.setattr(social,"_restart_social_runtime",lambda:None)
    captured={}
    class Vault:
        def __init__(self,path): captured["path"]=path
        def bind(self,binding,token):
            captured["binding"]=binding
            captured["token"]=token
    monkeypatch.setattr(social,"FileCredentialVault",Vault)

    result=social.bootstrap_account({"account_ref":"oursong_alstonhuang"})
    assert result["status"]=="BOUND"
    assert result["credential_migrated"] is True
    assert result["public_publish_performed"] is False
    assert captured["token"]=="super-secret-token"
    assert captured["binding"].product_id=="content-publish"
    encoded=json.dumps(result)
    assert "super-secret-token" not in encoded
    registry=json.loads((tmp_path/"accounts.json").read_text(encoding="utf-8"))
    item=registry["accounts"]["oursong_alstonhuang"]
    assert item["binding_id"]=="content-publish:threads:persona:123"
    assert "token" not in json.dumps(item).lower()


def test_successful_inspect_uses_shared_runtime_and_keeps_write_unknown(monkeypatch,tmp_path):
    monkeypatch.setattr(social,"ACCOUNT_CONFIG",config(tmp_path))
    registry=tmp_path/"accounts.json"
    registry.write_text(json.dumps({
        "schema":"agentos.content-publish-account-registry/v1",
        "accounts":{
            "oursong_alstonhuang":{
                "platform":"threads",
                "product_id":"content-publish",
                "binding_id":"content-publish:threads:persona:123",
                "provider_account_id":"123",
                "username":"oursong_alstonhuang",
            }
        }
    }),encoding="utf-8")
    monkeypatch.setattr(social,"ACCOUNT_REGISTRY",registry)
    monkeypatch.setattr(social,"_product_key",lambda product_id:"local-secret-key")
    seen={}
    def fake_post(path,payload,product_key):
        seen.update(path=path,payload=payload,key=product_key)
        return {
            "schema":"agentos.social-receipt/v1",
            "ok":True,
            "result":{"identity":{"provider_account_id":"123","username":"oursong_alstonhuang"}},
        }
    monkeypatch.setattr(social,"_post_runtime",fake_post)
    result=social.inspect_account({"account_ref":"oursong_alstonhuang"})
    assert result["status"]=="AUTHENTICATED"
    assert result["write_entitlement"]=="UNKNOWN"
    assert result["public_publish_performed"] is False
    assert seen["payload"]["product_id"]=="content-publish"
    assert seen["payload"]["account_binding_id"]=="content-publish:threads:persona:123"
    assert "local-secret-key" not in json.dumps(result)
