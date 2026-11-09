from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_core.experience_store import (
    converge_experience_set,
    digest_set,
    experience_path,
    read_experience_set,
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
        "provenance": {"sources": [], "accepted_evidence": []},
        "authority": {"status": "accepted", "supersedes": [], "superseded_by": []},
        "validity": {"conditions": [], "invalidated_by": []},
    }


def experience(summary: str) -> dict:
    return {
        "schema": "agentos.experience-set/v0",
        "project_id": "agentos-core",
        "artifacts": [artifact("core.test.v1", summary)],
    }


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def test_exact_predecessor_replaces_with_backup(tmp_path: Path):
    current = experience("before")
    incoming = experience("after")
    target = experience_path("agentos-core", data_root=tmp_path)
    seed = tmp_path / "seed.json"
    write_json(target, current)
    original = target.read_bytes()
    write_json(seed, incoming)

    receipt = converge_experience_set(
        seed,
        expected_current_digest=digest_set(current),
        data_root=tmp_path,
    )

    assert receipt["ok"] is True
    assert receipt["replaced"] is True
    assert receipt["previous_digest"] == digest_set(current)
    assert receipt["digest"] == digest_set(incoming)
    assert receipt["credential_exposed"] is False
    backup = Path(receipt["backup_path"])
    assert backup.read_bytes() == original
    assert read_experience_set("agentos-core", data_root=tmp_path) == incoming


def test_wrong_predecessor_refuses_without_mutation(tmp_path: Path):
    current = experience("before")
    incoming = experience("after")
    target = experience_path("agentos-core", data_root=tmp_path)
    seed = tmp_path / "seed.json"
    write_json(target, current)
    before = target.read_bytes()
    write_json(seed, incoming)

    with pytest.raises(ValueError, match="predecessor digest changed"):
        converge_experience_set(seed, expected_current_digest="sha256:" + "0" * 64, data_root=tmp_path)
    assert target.read_bytes() == before
    assert not list(target.parent.glob("accepted.pre-converge-*.json"))


def test_same_digest_is_idempotent_without_backup(tmp_path: Path):
    current = experience("same")
    target = experience_path("agentos-core", data_root=tmp_path)
    seed = tmp_path / "seed.json"
    write_json(target, current)
    write_json(seed, current)

    receipt = converge_experience_set(
        seed,
        expected_current_digest="sha256:" + "0" * 64,
        data_root=tmp_path,
    )
    assert receipt["replaced"] is False
    assert receipt["digest"] == digest_set(current)
    assert receipt["backup_path"] is None


def test_malformed_current_refuses(tmp_path: Path):
    target = experience_path("agentos-core", data_root=tmp_path)
    target.parent.mkdir(parents=True)
    target.write_text("{broken", encoding="utf-8")
    seed = tmp_path / "seed.json"
    write_json(seed, experience("after"))
    with pytest.raises(json.JSONDecodeError):
        converge_experience_set(seed, expected_current_digest="sha256:" + "0" * 64, data_root=tmp_path)


def test_symlink_target_refuses(tmp_path: Path):
    real = tmp_path / "real.json"
    write_json(real, experience("before"))
    target = experience_path("agentos-core", data_root=tmp_path)
    target.parent.mkdir(parents=True)
    target.symlink_to(real)
    seed = tmp_path / "seed.json"
    write_json(seed, experience("after"))
    with pytest.raises(ValueError, match="symlink"):
        converge_experience_set(seed, expected_current_digest=digest_set(experience("before")), data_root=tmp_path)
