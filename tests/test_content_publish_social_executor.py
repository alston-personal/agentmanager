from __future__ import annotations

import json

import pytest

from agentos_node import action_relay
from agentos_node.content_publish_social_executor import execute_preaccepted_threads
from runtime_core.content_publish_social import (
    build_threads_social_request,
    social_request_payload,
)


def request(**overrides):
    value={
        "schema":"agentos.content-publish/v1",
        "project_id":"zeus-writer",
        "platform":"threads",
        "account_ref":"oursong_alstonhuang",
        "content_ref":"artifact://zeus-writer/ch01/x",
        "mode":"publish",
        "authority":"approved-content-publish",
        "write_intent_id":"intent-threads-1",
    }
    value.update(overrides)
    return value


def artifact(**overrides):
    value={
        "schema":"agentos.content-artifact/v1",
        "title":"Chapter",
        "body":"fallback body",
        "media":[],
        "link":"",
        "hashtags":[],
        "reply":None,
        "metadata":{"platform_copy":{"threads":"threads-specific copy"}},
    }
    value.update(overrides)
    return value


def account(**overrides):
    value={
        "account_ref":"oursong_alstonhuang",
        "platform":"threads",
        "product_id":"content-publish",
        "binding_id":"content-publish:threads:persona:123",
        "provider_account_id":"123",
        "username":"oursong_alstonhuang",
    }
    value.update(overrides)
    return value


def test_projection_uses_product_specific_binding_and_write_intent():
    projected=build_threads_social_request(request(),artifact(),account())
    assert projected["product_id"]=="content-publish"
    assert projected["account_binding_id"]=="content-publish:threads:persona:123"
    assert projected["target_account_id"]=="123"
    assert projected["write_intent_id"]=="intent-threads-1"
    assert projected["primary_text"]=="threads-specific copy"
    assert len(projected["content_hash"])==64
    assert "authority" not in social_request_payload(projected)


def test_projection_fails_closed_for_unresolved_asset_media():
    with pytest.raises(ValueError,match="media_resolution_required"):
        build_threads_social_request(
            request(),
            artifact(media=[{"ref":"asset://cover/1","role":"cover"}]),
            account(),
        )


def test_projection_rejects_prepare_or_unapproved_authority():
    with pytest.raises(ValueError,match="publish_mode"):
        build_threads_social_request(request(mode="prepare"),artifact(),account())
    with pytest.raises(ValueError,match="authority_not_approved"):
        build_threads_social_request(request(authority="prepared-no-side-effect"),artifact(),account())


def test_projection_rejects_cross_product_binding():
    with pytest.raises(ValueError,match="product_scope"):
        build_threads_social_request(request(),artifact(),account(product_id="galaxy"))


def test_executor_requires_separately_supplied_acceptance(monkeypatch):
    monkeypatch.setattr("agentos_node.content_publish_social_executor._product_key",lambda:"product-key")
    with pytest.raises(PermissionError,match="acceptance_required"):
        execute_preaccepted_threads(
            request(),artifact(),acceptance_id="",account=account(),
        )


def test_executor_consumes_acceptance_without_exposing_it(monkeypatch):
    monkeypatch.setattr("agentos_node.content_publish_social_executor._product_key",lambda:"product-key")
    seen={}
    def fake(payload,*,acceptance_id,product_key):
        seen["payload"]=payload
        seen["acceptance_id"]=acceptance_id
        seen["product_key"]=product_key
        return {
            "schema":"agentos.social-receipt/v1",
            "ok":True,
            "platform_object_id":"threads-1",
            "permalink":"https://www.threads.net/@oursong_alstonhuang/post/threads-1",
        }
    receipt=execute_preaccepted_threads(
        request(),artifact(),acceptance_id="one-shot-authority",account=account(),runtime_call=fake,
    )
    assert seen["acceptance_id"]=="one-shot-authority"
    assert seen["payload"]["write_intent_id"]=="intent-threads-1"
    assert receipt["status"]=="PUBLISHED"
    assert receipt["result"]["public_publish_performed"] is True
    encoded=json.dumps(receipt)
    assert "one-shot-authority" not in encoded
    assert "product-key" not in encoded


def test_ambiguous_transport_result_requires_reconciliation(monkeypatch):
    monkeypatch.setattr("agentos_node.content_publish_social_executor._product_key",lambda:"product-key")
    def unknown(*args,**kwargs):
        raise RuntimeError("content_publish_social_execution_outcome_unknown")
    receipt=execute_preaccepted_threads(
        request(),artifact(),acceptance_id="one-shot-authority",account=account(),runtime_call=unknown,
    )
    assert receipt["status"]=="UNKNOWN"
    assert receipt["result"]["reconcile_required"] is True
    assert receipt["result"]["public_publish_performed"] is None


def test_preaccepted_executor_is_not_an_action_relay_surface():
    assert "agentos.content.social.publish.execute" not in action_relay.ACTIONS
