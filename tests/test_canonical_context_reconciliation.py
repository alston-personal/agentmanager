from pathlib import Path

import pytest

from agent_core.canonical_context import CanonicalContextStore


def seed_doc():
    return {
        "updated_at": "2026-08-27T00:00:00Z",
        "active_work": {
            "current_findings": ["native execution exists"],
            "next_actions": ["Validate Master Floor.", "Separate CI from execution."],
        },
    }


def test_checkpoint_is_durable_and_idempotent(tmp_path: Path):
    store = CanonicalContextStore(tmp_path / "core.sqlite3")
    store.seed("demo", seed_doc(), seed_revision="seed-1")
    first = store.checkpoint(
        "demo",
        checkpoint_id="receipt-1",
        task_id="task-1",
        completed_action="Validate Master Floor.",
        finding="gpt-5.4-mini low passed with no side effects.",
    )
    replay = store.checkpoint(
        "demo",
        checkpoint_id="receipt-1",
        task_id="ignored",
        completed_action="Separate CI from execution.",
        finding="must not apply",
    )
    assert replay == first
    restarted = CanonicalContextStore(tmp_path / "core.sqlite3")
    loaded = restarted.load("demo")
    assert loaded["_runtime_context"]["revision"] == 2
    assert loaded["active_work"]["next_actions"] == ["Separate CI from execution."]
    assert "must not apply" not in loaded["active_work"]["current_findings"]


def test_checkpoint_rejects_unproven_action(tmp_path: Path):
    store = CanonicalContextStore(tmp_path / "core.sqlite3")
    store.seed("demo", seed_doc())
    with pytest.raises(ValueError, match="not an active next_action"):
        store.checkpoint(
            "demo",
            checkpoint_id="receipt-x",
            task_id="task-x",
            completed_action="Invented work.",
            finding="fake evidence",
        )
