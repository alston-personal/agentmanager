"""Deterministic Context Compiler for AgentOS Core v0.1.

The compiler does not ask a model to summarize state. It selects durable facts
from project state and an optional development-context document into a compact,
stable execution-context contract suitable for any attached executor.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


CONTEXT_PROTOCOL = "agentos.execution-context/v0.1"


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _context_registry() -> dict[str, str]:
    raw_file = os.getenv("AGENTOS_PROJECT_CONTEXTS_FILE")
    if raw_file:
        value = _load_json(Path(raw_file).expanduser())
        if value:
            return {str(k): str(v) for k, v in value.items() if k and v}
    raw = os.getenv("AGENTOS_PROJECT_CONTEXTS_JSON", "{}")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(value, dict):
        return {}
    return {str(k): str(v) for k, v in value.items() if k and v}


def _development_context(project_id: str) -> dict[str, Any] | None:
    registry = _context_registry()
    configured = registry.get(project_id)
    if configured:
        return _load_json(Path(configured).expanduser())

    # The Core project itself may carry its canonical development context in
    # the deployed source tree without an explicit registry entry.
    if project_id == "agentmanager":
        root = Path(os.getenv("AGENT_PROJECT_ROOT", Path.cwd()))
        return _load_json(root / ".agentos" / "development-context.json")
    return None


def compile_execution_context(
    project_id: str,
    state: dict[str, Any],
    *,
    agent: dict[str, Any] | None = None,
) -> dict[str, Any]:
    document = _development_context(project_id) or {}
    active = document.get("active_work") if isinstance(document.get("active_work"), dict) else {}
    findings = active.get("current_findings") if isinstance(active.get("current_findings"), list) else []
    next_actions = active.get("next_actions") if isinstance(active.get("next_actions"), list) else []
    latest = state.get("latestTask") if isinstance(state.get("latestTask"), dict) else None

    goal = str(active.get("goal") or "").strip() or (
        str(state.get("currentIR", {}).get("goal") or "").strip()
        if isinstance(state.get("currentIR"), dict)
        else ""
    )
    recommended = str(state.get("recommendedAction") or "start")
    if next_actions:
        next_action = str(next_actions[0])
    elif recommended == "wait":
        next_action = "Wait for the current task receipt before deriving further work."
    elif recommended == "retry_or_continue":
        next_action = "Inspect the latest failed receipt, then retry or derive a recovery task."
    elif recommended == "continue":
        next_action = "Continue from the latest durable task/receipt state."
    else:
        next_action = "Derive the first task from the active goal and current canonical state."

    return {
        "schema": CONTEXT_PROTOCOL,
        "project_id": project_id,
        "agent": agent or {},
        "active_goal": goal or None,
        "recommended_action": recommended,
        "next_action": next_action,
        "current_findings": [str(x) for x in findings[:12]],
        "next_actions": [str(x) for x in next_actions[:8]],
        "latest_task": latest,
        "current_ir": state.get("currentIR"),
        "continuation": state.get("continuation"),
        "write_policy": document.get("write_policy") if isinstance(document.get("write_policy"), dict) else None,
        "integration_branch": active.get("integration_branch") or document.get("integration_branch"),
        "source_revision": document.get("updated_at"),
    }
