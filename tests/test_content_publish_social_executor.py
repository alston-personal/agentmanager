from __future__ import annotations

import json

import pytest

from agentos_node import action_relay
from agentos_node.content_publish_social_executor import execute_preaccepted_threads
from agentos_node.social.contracts import SocialRequest, social_request_digest
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


def media_envelope(**overrides):
    value={
        "schema":"agentos.media.asset.v0",
        "asset_id":"asset:zeus-cover-1",
        "owner_scope":"project:zeus-writer",
        "event_id":"zeus-ch01-cover",
        "content":{
            "mime":"image/jpeg",
            "sha256":"a"*64,
            "byte_length":12345,
        },
        "locations":[
            {
                "kind":"public_https",
                "uri":"https://studio.milkcat.org/media/zeus/ch01-cover.jpg",
                "expires_at":None,
            }
        ],
        "provenance":{"source":"user_upload","generator":None,"inputs":[],"scene_source":None},
        "rights":{
            "owner":"zeus-writer",
            "license":"owned",
            "publication_allowed":True,
            "commercial_allowed":True,
        },
        "integrity":{
            "background_preserved":None,
            "identity_reference_checked":None,
            "human_approved":True,
        },
        "state":"approved",
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


def test_projection_resolves_only_approved_portable_media():
    ref="asset://zeus-writer/fragment/ch01/cover"
    art=artifact(media=[{"ref":ref,"role":"cover","alt":"章節封面"}])
    projected=build_threads_social_request(
        request(),
        art,
        account(),
        media_resolutions={ref:media_envelope()},
    )
    assert projected["image_url"]=="https://studio.milkcat.org/media/zeus/ch01-cover.jpg"
    assert projected["image_alt_text"]=="章節封面"
    assert projected["media_resolution"]==[{
        "asset_ref":ref,
        "asset_id":"asset:zeus-cover-1",
        "owner_scope":"project:zeus-writer",
        "mime":"image/jpeg",
        "sha256":"a"*64,
        "public_url":"https://studio.milkcat.org/media/zeus/ch01-cover.jpg",
    }]


@pytest.mark.parametrize(
    "envelope,error",
    [
        (media_envelope(rights={"owner":"zeus-writer","license":"owned","publication_allowed":False,"commercial_allowed":True}),"publication_not_allowed"),
        (media_envelope(integrity={"background_preserved":None,"identity_reference_checked":None,"human_approved":False}),"not_human_approved"),
        (media_envelope(state="draft"),"state_not_approved"),
        (media_envelope(locations=[]),"public_https_delivery_required"),
    ],
)
def test_projection_rejects_unapproved_or_undeliverable_media(envelope,error):
    ref="asset://zeus-writer/fragment/ch01/cover"
    with pytest.raises((ValueError,PermissionError),match=error):
        build_threads_social_request(
            request(),
            artifact(media=[{"ref":ref,"role":"cover"}]),
            account(),
            media_resolutions={ref:envelope},
        )


def test_delivery_url_change_keeps_artifact_hash_but_changes_social_request_digest():
    ref="asset://zeus-writer/fragment/ch01/cover"
    art=artifact(media=[{"ref":ref,"role":"cover"}])
    one=build_threads_social_request(
        request(),art,account(),media_resolutions={ref:media_envelope()}
    )
    two_env=media_envelope(locations=[{
        "kind":"public_https",
        "uri":"https://studio.milkcat.org/media/zeus/ch01-cover-v2.jpg",
        "expires_at":None,
    }])
    two=build_threads_social_request(
        request(),art,account(),media_resolutions={ref:two_env}
    )
    assert one["content_hash"]==two["content_hash"]
    assert one["image_url"]!=two["image_url"]
    one_req=SocialRequest(**social_request_payload(one))
    two_req=SocialRequest(**social_request_payload(two))
    assert social_request_digest(one_req)!=social_request_digest(two_req)


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


def test_executor_uses_resolved_media_without_exposing_acceptance(monkeypatch):
    monkeypatch.setattr("agentos_node.content_publish_social_executor._product_key",lambda:"product-key")
    ref="asset://zeus-writer/fragment/ch01/cover"
    seen={}
    def fake(payload,*,acceptance_id,product_key):
        seen["payload"]=payload
        return {
            "schema":"agentos.social-receipt/v1",
            "ok":True,
            "platform_object_id":"threads-image-1",
            "permalink":"https://www.threads.net/@oursong_alstonhuang/post/threads-image-1",
        }
    receipt=execute_preaccepted_threads(
        request(),
        artifact(media=[{"ref":ref,"role":"cover","alt":"封面"}]),
        acceptance_id="one-shot-authority",
        account=account(),
        media_resolutions={ref:media_envelope()},
        runtime_call=fake,
    )
    assert seen["payload"]["image_url"].startswith("https://")
    assert "asset://" not in json.dumps(seen["payload"])
    assert receipt["result"]["media_resolution"][0]["asset_id"]=="asset:zeus-cover-1"
    assert "one-shot-authority" not in json.dumps(receipt)


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
