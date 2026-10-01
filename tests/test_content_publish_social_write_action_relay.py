from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentos_node import content_publish_social_write_action_relay as write


HASH="a"*64


def request(**overrides):
    value={
        "schema":write.WRITE_SCHEMA,
        "project_id":"zeus-writer",
        "platform":"threads",
        "account_ref":"oursong_alstonhuang",
        "operation":"publish",
        "primary_text":"test content",
        "write_intent_id":"zeus-1234567890abcdef12345678",
        "content_hash":HASH,
        "authority":"approved-content-publish",
    }
    value.update(overrides)
    return value


@pytest.fixture(autouse=True)
def account(monkeypatch,tmp_path):
    monkeypatch.setattr(write,"INTENT_ROOT",tmp_path/"intents")
    monkeypatch.setattr(
        write.social_bootstrap,
        "_load_account_config",
        lambda ref: {
            "account_ref":ref,
            "platform":"threads",
            "product_id":"content-publish",
        } if ref=="oursong_alstonhuang" else (_ for _ in ()).throw(ValueError("unknown")),
    )
    monkeypatch.setattr(
        write.social_bootstrap,
        "_load_registry",
        lambda: {
            "schema":"agentos.content-publish-account-registry/v1",
            "accounts":{
                "oursong_alstonhuang":{
                    "platform":"threads",
                    "product_id":"content-publish",
                    "binding_id":"content-publish:threads:persona:123",
                    "provider_account_id":"123",
                    "username":"oursong_alstonhuang",
                }
            },
        },
    )
    monkeypatch.setattr(write.social_bootstrap,"_product_key",lambda product:"product-secret")
    monkeypatch.setattr(write,"_control_token",lambda:"control-secret")


def test_contract_rejects_extra_secret_endpoint_and_unapproved_authority():
    for key,value in [
        ("token","x"),
        ("endpoint","https://evil.invalid"),
        ("shell","rm -rf /"),
    ]:
        with pytest.raises(ValueError):
            write._validate_request({**request(),key:value})
    with pytest.raises(PermissionError):
        write._validate_request(request(authority="prepared-no-side-effect"))
    with pytest.raises(ValueError):
        write._validate_request(request(project_id="other-project"))


def test_reply_requires_target_and_forbids_media():
    with pytest.raises(ValueError):
        write._validate_request(request(operation="reply"))
    with pytest.raises(ValueError):
        write._validate_request(request(
            operation="reply",
            reply_to_id="123",
            image_url="https://example.com/a.png",
            image_alt_text="a",
        ))


def test_publish_is_idempotent_across_new_capsules(monkeypatch):
    calls=[]
    def post(path,payload,headers,timeout=20):
        calls.append((path,dict(headers)))
        if path.endswith("/acceptances"):
            return 201,{"acceptance_id":"one-shot"}
        return 200,{
            "schema":"agentos.social-receipt/v1",
            "ok":True,
            "platform_object_id":"thread-1",
            "permalink":"https://www.threads.net/@oursong_alstonhuang/post/thread-1",
        }
    monkeypatch.setattr(write,"_post_json",post)

    first=write.execute_write(request())
    second=write.execute_write(request())
    assert first["status"]=="published"
    assert second["status"]=="published"
    assert second["deduplicated"] is True
    assert [p for p,_ in calls].count("/v1/social/publish")==1
    assert "product-secret" not in json.dumps(second)
    assert "control-secret" not in json.dumps(second)


def test_failure_after_acceptance_becomes_unknown_and_never_blind_retries(monkeypatch):
    calls=[]
    def post(path,payload,headers,timeout=20):
        calls.append(path)
        if path.endswith("/acceptances"):
            return 201,{"acceptance_id":"one-shot"}
        raise RuntimeError("transport lost after effect may have happened")
    monkeypatch.setattr(write,"_post_json",post)

    first=write.execute_write(request())
    second=write.execute_write(request())
    assert first["status"]=="unknown"
    assert first["reconcile_required"] is True
    assert second["status"]=="unknown"
    assert calls.count("/v1/social/publish")==1
    assert calls.count("/internal/v1/social/acceptances")==1


def test_acceptance_failure_is_explicitly_safe_to_retry(monkeypatch):
    calls=[]
    def post(path,payload,headers,timeout=20):
        calls.append(path)
        raise RuntimeError("control plane unavailable")
    monkeypatch.setattr(write,"_post_json",post)
    first=write.execute_write(request())
    second=write.execute_write(request())
    assert first["status"]=="authority_unavailable"
    assert first["safe_to_retry"] is True
    assert second["status"]=="authority_unavailable"
    assert calls.count("/internal/v1/social/acceptances")==2
    assert "/v1/social/publish" not in calls


def test_same_write_intent_with_different_content_is_conflict(monkeypatch):
    monkeypatch.setattr(
        write,
        "_post_json",
        lambda path,payload,headers,timeout=20: (
            (201,{"acceptance_id":"one-shot"})
            if path.endswith("/acceptances")
            else (200,{"ok":True,"platform_object_id":"1"})
        ),
    )
    write.execute_write(request())
    with pytest.raises(RuntimeError,match="intent_conflict"):
        write.execute_write(request(primary_text="different"))
