import pytest

from runtime_core.content_publish import (
    CONTENT_ARTIFACT_SCHEMA,
    PUBLISH_REQUEST_SCHEMA,
    PUBLISH_BATCH_SCHEMA,
    ProviderHealth,
    ProviderRecord,
    ProviderRegistry,
    ResolutionStatus,
    build_publish_receipt,
    content_hash,
    validate_publish_request,
    validate_publish_batch,
)


def artifact(**overrides):
    value = {
        "schema": CONTENT_ARTIFACT_SCHEMA,
        "title": "hello",
        "body": "body",
        "media": [],
        "link": "",
        "hashtags": [],
        "reply": None,
        "metadata": {},
    }
    value.update(overrides)
    return value


def request(**overrides):
    value = {
        "schema": PUBLISH_REQUEST_SCHEMA,
        "project_id": "zeus-writer",
        "platform": "x",
        "account_ref": "oursong_alston",
        "content_ref": "artifact://chapter/1",
        "mode": "publish",
        "authority": "approved-content-publish",
        "write_intent_id": "intent-1",
    }
    value.update(overrides)
    return value


def provider(provider_id, *, health="READY", unattended=True, priority=0, media=True, reply=True):
    return ProviderRecord.from_mapping({
        "provider_id": provider_id,
        "platform": "x",
        "transport": provider_id,
        "health": health,
        "auth_state": health,
        "capabilities": ["publish", "prepare"],
        "supports_media": media,
        "supports_reply": reply,
        "supports_thread": False,
        "supports_unattended_publish": unattended,
        "account_refs": ["oursong_alston"],
        "priority": priority,
    })


def test_request_rejects_raw_credentials_and_executable_fields_recursively():
    with pytest.raises(ValueError):
        validate_publish_request({**request(), "metadata": {"token": "secret"}})
    with pytest.raises(ValueError):
        validate_publish_request({**request(), "browser_javascript": "click()"})


def test_request_requires_artifact_reference():
    with pytest.raises(ValueError):
        validate_publish_request({**request(), "content_ref": "/tmp/body.txt"})


def test_resolver_prefers_ready_unattended_api():
    registry = ProviderRegistry([
        provider("x-web-assist", unattended=False, priority=50),
        provider("x-api", unattended=True, priority=10),
    ])
    resolved = registry.resolve(request(), artifact=artifact())
    assert resolved.status is ResolutionStatus.READY
    assert resolved.provider_id == "x-api"


def test_resolver_falls_back_to_web_assist_with_human_confirmation():
    registry = ProviderRegistry([
        provider("x-api", health="ENTITLEMENT_REQUIRED", unattended=True, priority=100),
        provider("x-web-assist", unattended=False, priority=50),
    ])
    resolved = registry.resolve(request(), artifact=artifact())
    assert resolved.status is ResolutionStatus.HUMAN_CONFIRM_REQUIRED
    assert resolved.provider_id == "x-web-assist"
    assert resolved.confirmation_required is True


def test_resolver_reports_entitlement_state_when_no_ready_fallback():
    registry = ProviderRegistry([
        provider("x-api", health="ENTITLEMENT_REQUIRED", unattended=True),
    ])
    resolved = registry.resolve(request(), artifact=artifact())
    assert resolved.status is ResolutionStatus.ENTITLEMENT_REQUIRED


def test_media_requirement_excludes_non_media_provider():
    registry = ProviderRegistry([
        provider("x-text-only", media=False),
    ])
    resolved = registry.resolve(request(), artifact=artifact(media=[{"ref": "asset://image/1"}]))
    assert resolved.status is ResolutionStatus.CAPABILITY_UNAVAILABLE


def test_content_hash_is_stable():
    assert content_hash(artifact()) == content_hash(dict(reversed(list(artifact().items()))))


def test_receipt_sanitizes_nested_credentials():
    receipt = build_publish_receipt(
        platform="x",
        provider="x-api",
        account_ref="oursong_alston",
        status="published",
        write_intent_id="intent-1",
        artifact=artifact(),
        result={"object_id": "1", "nested": {"token": "nope", "permalink": "https://x.com/a/status/1"}},
    )
    assert receipt["credential_exposed"] is False
    assert "token" not in receipt["result"]["nested"]
    assert receipt["result"]["object_id"] == "1"


def test_publish_mode_requires_write_intent_id():
    with pytest.raises(ValueError):
        validate_publish_request({**request(), "write_intent_id": None})


def test_artifact_rejects_local_media_path():
    with pytest.raises(ValueError):
        content_hash(artifact(media=[{"ref": "/tmp/cover.png"}]))


def test_batch_contract_normalizes_independent_targets():
    batch = validate_publish_batch({
        "schema": PUBLISH_BATCH_SCHEMA,
        "project_id": "zeus-writer",
        "content_ref": "artifact://chapter/1",
        "targets": [
            {
                "platform": "threads",
                "account_ref": "oursong_alstonhuang",
                "mode": "prepare",
                "authority": "prepared-no-side-effect",
                "write_intent_id": "intent-threads",
                "required": "best_effort",
            },
            {
                "platform": "x",
                "account_ref": "oursong_alston",
                "mode": "publish",
                "authority": "approved-content-publish",
                "write_intent_id": "intent-x",
                "required": "optional",
            },
        ],
    })
    assert batch["schema"] == PUBLISH_BATCH_SCHEMA
    assert [x["platform"] for x in batch["targets"]] == ["threads", "x"]


def test_batch_rejects_duplicate_platform_account():
    target = {
        "platform": "x",
        "account_ref": "oursong_alston",
        "mode": "prepare",
        "authority": "prepared-no-side-effect",
        "write_intent_id": "intent-x",
    }
    with pytest.raises(ValueError):
        validate_publish_batch({
            "schema": PUBLISH_BATCH_SCHEMA,
            "project_id": "zeus-writer",
            "content_ref": "artifact://chapter/1",
            "targets": [target, dict(target)],
        })


def test_receipt_sanitizes_suffix_secret_fields():
    receipt = build_publish_receipt(
        platform="x",
        provider="x-api",
        account_ref="oursong_alston",
        status="prepared",
        result={"nested": {"provider_access_token": "nope", "client_secret": "nope", "safe": "yes"}},
    )
    assert receipt["result"]["nested"] == {"safe": "yes"}
