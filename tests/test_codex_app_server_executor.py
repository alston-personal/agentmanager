from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from agentos_node.codex_app_server_executor import BoundedCodexExecutor, RECEIPT_SCHEMA
from agentos_node.remote_worker import build_default_worker


class FakeSession:
    def __init__(self, *, forbidden: list[str] | None = None) -> None:
        self.forbidden = forbidden or []
        self.call: dict[str, Any] | None = None

    def run(self, *, model: str, effort: str, cwd: Path, prompt: str, timeout_seconds: int) -> dict[str, Any]:
        self.call = {
            "model": model,
            "effort": effort,
            "cwd": cwd,
            "prompt": prompt,
            "timeout_seconds": timeout_seconds,
        }
        return {
            "thread_id": "thread-test",
            "turn_id": "turn-test",
            "output_text": "continue safely",
            "item_types": ["userMessage", "reasoning", "agentMessage"],
            "server_requests": [],
            "forbidden_items": self.forbidden,
        }


def working_set(project_id: str = "demo") -> dict[str, Any]:
    return {
        "schema": "agentos.executor-working-set/v0.1",
        "project_id": project_id,
        "active_goal": "continue Core v0.1",
        "next_action": "implement bounded executor",
        "current_findings": ["Master Floor passed"],
        "next_actions": ["implement bounded executor"],
        "write_policy": {"experimental_writes_to_main": "deny"},
    }


def test_executor_is_admin_model_owned_and_read_only_prompted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENTOS_CODEX_EXECUTOR_MODEL", "gpt-5.4-mini")
    monkeypatch.setenv("AGENTOS_CODEX_EXECUTOR_EFFORT", "low")
    fake = FakeSession()
    receipt = BoundedCodexExecutor(session=fake).execute(
        project_id="demo",
        working_set=working_set(),
        instruction="Return the safe next action.",
    )
    assert receipt["schema"] == RECEIPT_SCHEMA
    assert receipt["model"] == "gpt-5.4-mini"
    assert receipt["reasoning_effort"] == "low"
    assert receipt["thread_id"] == "thread-test"
    assert receipt["turn_id"] == "turn-test"
    assert receipt["side_effect_audit"]["no_side_effects"] is True
    assert fake.call is not None
    assert "Do not inspect files, run commands, call tools, modify anything" in fake.call["prompt"]
    assert fake.call["cwd"].name.startswith("agentos-codex-bounded-")


def test_executor_rejects_cross_project_and_side_effects() -> None:
    with pytest.raises(ValueError, match="project_id"):
        BoundedCodexExecutor(session=FakeSession()).execute(
            project_id="other",
            working_set=working_set("demo"),
            instruction="answer",
        )
    with pytest.raises(RuntimeError, match="side-effect audit"):
        BoundedCodexExecutor(session=FakeSession(forbidden=["commandExecution"])).execute(
            project_id="demo",
            working_set=working_set(),
            instruction="answer",
        )


def test_worker_registers_bounded_codex_capability() -> None:
    worker = build_default_worker("oracle-core-node")
    assert "agentos.executor.codex" in worker.capabilities
