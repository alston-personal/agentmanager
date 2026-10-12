from __future__ import annotations

from pathlib import Path
import json

from agent_core.experience_store import experience_path, digest_set

import pytest

from agent_core.experience_growth_ledger import (
    append_attempt,
    classify_delta,
    growth_status,
)


def artifact(experience_id: str, summary: str) -> dict:
    return {
        "schema": "agentos.experience/v0",
        "experience_id": experience_id,
        "project_id": "agentos-core",
        "realm_scope": ["*"],
        "capability_scope": ["agentos.core.develop"],
        "executor_scope": ["*"],
        "kind": "decision",
        "summary": summary,
        "payload": {},
        "provenance": {"sources": ["test"], "accepted_evidence": []},
        "authority": {"status": "accepted", "supersedes": [], "superseded_by": []},
        "validity": {"conditions": [], "invalidated_by": []},
    }


def experience(*artifacts: dict) -> dict:
    return {
        "schema": "agentos.experience-set/v0",
        "project_id": "agentos-core",
        "artifacts": list(artifacts),
    }


def test_delta_distinguishes_new_update_and_noop() -> None:
    before = experience(artifact("core.a.v1", "a"))
    added = experience(artifact("core.a.v1", "a"), artifact("core.b.v1", "b"))
    changed = experience(artifact("core.a.v1", "changed"))
    same = experience(artifact("core.a.v1", "a"))

    assert classify_delta(before, added)["classification"] == "accepted_new"
    update = classify_delta(before, changed)
    assert update["classification"] == "accepted_update"
    assert update["updated_ids"] == ["core.a.v1"]
    assert classify_delta(before, same)["classification"] == "duplicate_noop"


def test_attempt_is_idempotent_and_status_is_queryable(tmp_path: Path) -> None:
    args = dict(
        project_id="agentos-core",
        attempt_id="attempt-1",
        executor_id="participant://agent/gemini-oracle",
        source_node="oracle",
        classification="accepted_new",
        timestamp="2026-10-12T03:30:00Z",
        source_receipt="receipt://one/attempt-1",
        persisted_experience_ids=["core.a.v1"],
        before_count=0,
        after_count=1,
        before_digest="sha256:" + "0" * 64,
        after_digest="sha256:" + "1" * 64,
        growth_proof_status="UNTESTED",
        data_root=tmp_path,
    )

    canonical = experience(artifact("core.a.v1", "a"))
    store_path = experience_path("agentos-core", data_root=tmp_path)
    store_path.parent.mkdir(parents=True, exist_ok=True)
    store_path.write_text(json.dumps(canonical), encoding="utf-8")
    args["after_digest"] = digest_set(canonical)

    first = append_attempt(**args)
    second = append_attempt(**args)
    assert first["appended"] is True
    assert second["appended"] is False

    status = growth_status(
        "agentos-core",
        executor_id="participant://agent/gemini-oracle",
        source_node="oracle",
        data_root=tmp_path,
    )
    assert status["attempt_count"] == 1
    assert status["accepted_attempt_count"] == 1
    assert status["last_success"]["attempt_id"] == "attempt-1"
    assert status["credential_exposed"] is False


def test_same_attempt_id_cannot_be_reused_for_different_claim(tmp_path: Path) -> None:
    common = dict(
        project_id="agentos-core",
        attempt_id="attempt-1",
        executor_id="participant://agent/gemini-oracle",
        source_node="oracle",
        timestamp="2026-10-12T03:30:00Z",
        data_root=tmp_path,
    )
    append_attempt(classification="asserted_only", **common)
    with pytest.raises(ValueError, match="different content"):
        append_attempt(classification="accepted_new", **common)


def test_assertion_does_not_count_as_one_side_success(tmp_path: Path) -> None:
    append_attempt(
        project_id="agentos-core",
        attempt_id="attempt-assertion",
        executor_id="participant://agent/gemini-vopc5750",
        source_node="vopc5750",
        classification="asserted_only",
        timestamp="2026-10-12T03:31:00Z",
        data_root=tmp_path,
    )
    status = growth_status(
        "agentos-core",
        executor_id="participant://agent/gemini-vopc5750",
        data_root=tmp_path,
    )
    assert status["attempt_count"] == 1
    assert status["accepted_attempt_count"] == 0
    assert status["last_success"] is None


def test_claimed_accepted_experience_requires_matching_one_snapshot(tmp_path: Path) -> None:
    canonical = experience(artifact("core.a.v1", "a"))
    path = experience_path("agentos-core", data_root=tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(canonical), encoding="utf-8")
    args = dict(
        project_id="agentos-core", attempt_id="unverified-1",
        executor_id="gemini-oracle", source_node="oracle",
        classification="accepted_new", timestamp="2026-10-12T03:35:00Z",
        source_receipt="receipt://one/unverified-1",
        persisted_experience_ids=["core.a.v1"], before_count=0,
        after_count=1, data_root=tmp_path,
    )
    with pytest.raises(ValueError, match="digest"):
        append_attempt(after_digest="sha256:" + "0" * 64, **args)
    with pytest.raises(ValueError, match="count"):
        append_attempt(after_digest=digest_set(canonical), **{**args, "after_count": 2})
    with pytest.raises(ValueError, match="IDs"):
        append_attempt(after_digest=digest_set(canonical), **{**args, "persisted_experience_ids": ["not-present"]})
    assert growth_status("agentos-core", data_root=tmp_path)["attempt_count"] == 0
