from __future__ import annotations

from copy import deepcopy

import pytest

from agent_core.experience import (
    ExperienceContractError,
    ExperienceQuery,
    discover_experience,
    experience_semantic_digest,
    hydrate_experience,
    validate_extraction_proposal,
)


def artifact(experience_id: str, *, status: str = "accepted"):
    return {
        "schema": "agentos.experience/v1",
        "experience_id": experience_id,
        "project_id": "agentos-core",
        "realm_scope": ["oracle"],
        "capability_scope": ["agentos.one.resolve"],
        "executor_scope": [],
        "kind": "constraint",
        "ir": {
            "schema": "agentos.experience-ir/v1",
            "nodes": [
                {
                    "id": "authority",
                    "op": "require",
                    "predicate": "continuation.authority",
                    "arguments": [{"type": "symbol", "value": "ONE_CANONICAL_IR"}],
                },
                {
                    "id": "workspace",
                    "op": "forbid",
                    "predicate": "continuation.authority",
                    "arguments": [{"type": "symbol", "value": "WORKSPACE_VENDOR_HISTORY"}],
                },
            ],
            "entrypoints": ["authority", "workspace"],
            "expected_behavior_dimensions": ["workspace_is_continuation_authority"],
        },
        "display": {"summary": f"Human label for {experience_id}"},
        "provenance": {
            "sources": ["issue://152"],
            "accepted_evidence": ["evidence://continuity/e3"],
            "extraction_id": "extract://152/authority",
        },
        "authority": {
            "status": status,
            "supersedes": [],
            "superseded_by": [],
        },
        "validity": {"conditions": [], "invalidated_by": []},
    }


def test_summary_is_optional_and_non_authoritative():
    item = artifact("authority.v1")
    first = experience_semantic_digest(item)
    item["display"]["summary"] = "A completely different human explanation"
    second = experience_semantic_digest(item)
    assert first == second

    del item["display"]
    third = experience_semantic_digest(item)
    assert first == third


def test_semantic_change_changes_digest():
    item = artifact("authority.v1")
    first = experience_semantic_digest(item)
    item["ir"]["nodes"][0]["arguments"][0]["value"] = "WORKSPACE_VENDOR_HISTORY"
    assert experience_semantic_digest(item) != first


def test_hydration_contains_ir_and_expected_dimensions_not_summary_payload():
    item = artifact("authority.v1")
    projection = hydrate_experience(
        project_id="agentos-core",
        active_goal="continue Core integration",
        artifacts=[item],
    ).as_dict()
    hydrated = projection["items"][0]
    assert hydrated["experience_id"] == "authority.v1"
    assert hydrated["ir"]["schema"] == "agentos.experience-ir/v1"
    assert hydrated["expected_behavior_dimensions"] == ["workspace_is_continuation_authority"]
    assert "summary" not in hydrated
    assert "payload" not in hydrated


def test_discovery_filters_candidates_and_preserves_scope():
    accepted = artifact("accepted")
    candidate = artifact("candidate", status="candidate")
    result = discover_experience(
        [candidate, accepted],
        ExperienceQuery(
            project_id="agentos-core",
            realm="oracle",
            capabilities=("agentos.one.resolve",),
            executor="codex",
        ),
    )
    assert [item["experience_id"] for item in result] == ["accepted"]


def test_rejects_sensitive_ir():
    item = artifact("bad")
    item["ir"]["nodes"][0]["value"] = {
        "type": "object",
        "value": {"token": "must-not-enter-experience"},
    }
    with pytest.raises(ExperienceContractError, match="sensitive credential"):
        experience_semantic_digest(item)


def test_extraction_proposal_cannot_self_authorize():
    candidate = artifact("candidate", status="candidate")
    proposal = {
        "schema": "agentos.experience-extraction/v1",
        "extraction_id": "extract-1",
        "project_id": "agentos-core",
        "origin": {"node_id": "oracle", "surface": "codex"},
        "sources": ["issue://152", "receipt://e3"],
        "abstraction": {
            "generalized_from": ["canonical continuation authority evidence"],
            "excluded": ["vendor-local workspace history"],
        },
        "candidate": candidate,
    }
    validate_extraction_proposal(proposal)
    accepted = deepcopy(proposal)
    accepted["candidate"]["authority"]["status"] = "accepted"
    with pytest.raises(ExperienceContractError, match="must not self-authorize"):
        validate_extraction_proposal(accepted)
