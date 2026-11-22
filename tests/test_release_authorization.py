"""Denied release cases are deterministic, independent of any write-capable Runtime."""
from datetime import datetime, timedelta, timezone

import pytest

from agent_core.release_authorization import verify_release_intent

NOW = datetime(2026, 11, 22, 12, 0, tzinfo=timezone.utc)
SHA = "a" * 40
DIGEST = "sha256:" + "b" * 64


def scenario():
    request = {
        "source_ref": "main", "source_commit": SHA,
        "repository": "alston-personal/agentmanager",
        "project_id": "agentos-core", "realm_id": "realm-production",
        "environment": "oracle-production", "operation": "runtime.converge",
        "authenticated_principal": "workflow-issuer:1234", "release_epoch": 8,
    }
    intent = {
        "schema": "agentos.approved-release-intent/v1", "state": "approved",
        "source_ref": "main", "source_commit": SHA,
        "repository": request["repository"], "project_id": request["project_id"],
        "realm_id": request["realm_id"], "environment": request["environment"],
        "operation": request["operation"], "authorized_principal": request["authenticated_principal"],
        "release_epoch": 8, "artifact_digest": DIGEST,
        "approval_receipt_id": "approved-human-8",
        "expires_at": (NOW + timedelta(minutes=5)).isoformat(),
    }
    target = {
        "repository": request["repository"],
        "environment": request["environment"],
        "realm_id": request["realm_id"], "release_epoch": 7,
    }
    return request, intent, target


def test_only_matching_trusted_approval_and_newer_epoch_are_eligible():
    request, approved, target = scenario()
    result = verify_release_intent(
        request=request, approved_intent=approved, observed_target=target, now=NOW)
    assert result.allowed is True
    assert result.release_epoch == 8
    assert "requires_atomic_target_cas" in result.reason


@pytest.mark.parametrize("mutation,reason", [
    (("request", "source_ref", "core/integration"), "non_main_source_forbidden"),
    (("request", "source_commit", "c" * 40), "source_commit_not_approved"),
    (("intent", "source_ref", "core/integration"), "non_main_intent_forbidden"),
    (("intent", "state", "draft"), "release_not_approved"),
    (("intent", "artifact_digest", ""), "missing_immutable_artifact_digest"),
    (("intent", "approval_receipt_id", ""), "missing_approval_receipt"),
    (("request", "authenticated_principal", "legacy-executor"), "principal_not_authorized"),
    (("request", "realm_id", "other-realm"), "scope_mismatch_realm_id"),
    (("request", "operation", "social.deploy"), "scope_mismatch_operation"),
    (("request", "release_epoch", 7), "request_epoch_mismatch"),
    (("target", "release_epoch", 8), "stale_release_epoch"),
    (("target", "release_epoch", 9), "stale_release_epoch"),
    (("intent", "release_epoch", True), "invalid_release_epoch"),
    (("intent", "expires_at", "2026-11-22T11:59:59Z"), "intent_expired"),
])
def test_rejects_unapproved_source_and_concurrent_epochs(mutation, reason):
    request, approved, target = scenario()
    where, key, value = mutation
    {"request": request, "intent": approved, "target": target}[where][key] = value
    result = verify_release_intent(
        request=request, approved_intent=approved, observed_target=target, now=NOW)
    assert result.allowed is False
    assert result.reason == reason


def test_missing_authoritative_data_fails_closed():
    request, approved, target = scenario()
    assert verify_release_intent(
        request=request, approved_intent=None, observed_target=target,
        now=NOW).reason == "missing_trusted_release_intent"
    assert verify_release_intent(
        request=request, approved_intent=approved, observed_target=None,
        now=NOW).reason == "missing_trusted_target_epoch"


def test_request_must_not_supply_self_approved_intent():
    request, approved, target = scenario()
    request["approved_intent"] = approved
    assert verify_release_intent(
        request=request, approved_intent=None, observed_target=target,
        now=NOW).allowed is False
