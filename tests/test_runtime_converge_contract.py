from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_core.runtime_converge_contract import (
    ALLOWED_REPOSITORY,
    CAPABILITY,
    SCHEMA,
    validate_runtime_converge_request,
)


ROOT = Path(__file__).resolve().parent.parent
POLICY = ROOT / "governance" / "runtime-converge.json"
SHA = "45e63abc3e806ecc0547f93330584e1e387e0757"


def request(**overrides):
    payload = {
        "schema": SCHEMA,
        "request_id": "runtime-converge-test-1",
        "node_id": "oracle-core-node",
        "repository": ALLOWED_REPOSITORY,
        "source_ref": "core/integration",
        "source_commit": SHA,
    }
    payload.update(overrides)
    return payload


def test_policy_is_fail_closed_and_one_direct():
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    assert policy["capability"] == CAPABILITY
    assert policy["target_node_ids"] == ["oracle-core-node"]
    assert policy["allowed_repository"] == ALLOWED_REPOSITORY
    assert policy["allowed_source_refs"] == ["core/integration"]
    assert policy["require_exact_commit"] is True
    assert policy["require_clean_tracked_checkout"] is True
    assert policy["require_health_check"] is True
    assert policy["rollback_on_failed_health"] is True
    assert policy["steady_state_transport"] == "one_direct"
    assert policy["ambiguous_state"] == "unknown_no_blind_retry"
    assert "github_actions_is_not_steady_state_control_plane" in policy["invariants"]


def test_valid_request_is_normalized_without_execution_carrier():
    validated = validate_runtime_converge_request(request())
    assert validated.node_id == "oracle-core-node"
    assert validated.repository == ALLOWED_REPOSITORY
    assert validated.source_ref == "core/integration"
    assert validated.source_commit == SHA
    assert set(validated.as_payload()) == {
        "schema", "request_id", "node_id", "repository", "source_ref", "source_commit"
    }


@pytest.mark.parametrize("field", ["shell", "script", "argv", "module", "executable", "command", "token", "credentials", "environment"])
def test_execution_and_credential_fields_fail_closed(field):
    with pytest.raises(ValueError, match="runtime_converge_forbidden_fields"):
        validate_runtime_converge_request(request(**{field: "forbidden"}))


def test_wrong_node_repo_ref_or_sha_fail_closed():
    cases = [
        (request(node_id="vopc5750"), "node_not_allowed"),
        (request(repository="alston-personal/zeus-writer"), "repository_not_allowed"),
        (request(source_ref="main"), "source_ref_not_allowed"),
        (request(source_commit="abc"), "source_commit_invalid"),
        (request(source_commit=SHA.upper()), "source_commit_invalid"),
    ]
    for payload, message in cases:
        with pytest.raises(ValueError, match=message):
            validate_runtime_converge_request(payload)


def test_extra_unknown_field_fails_closed():
    with pytest.raises(ValueError, match="request_shape_invalid"):
        validate_runtime_converge_request(request(auto_converge=False))
