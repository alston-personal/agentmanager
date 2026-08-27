"""Deterministic Context Compiler for AgentOS Core v0.1.

The compiler does not ask a model to summarize state. It selects durable facts
from project state and an optional development-context document into a compact,
stable execution-context contract suitable for any attached executor.

Repository development-context files are seeds/snapshots. When a runtime
CanonicalContextStore is supplied, the compiler seeds it once and thereafter
prefers the mutable data-layer context owned by the Kernel.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any

from .canonical_context import CanonicalContextStore


CONTEXT_PROTOCOL = "agentos.execution-context/v0.1"
WORKING_SET_PROTOCOL = "agentos.executor-working-set/v0.1"
DEFAULT_CONTEXT_MAX_AGE_SECONDS = 24 * 60 * 60


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


def _source_development_context(project_id: str) -> dict[str, Any] | None:
    registry = _context_registry()
    configured = registry.get(project_id)
    if configured:
        return _load_json(Path(configured).expanduser())

    if project_id == "agentmanager":
        root = Path(os.getenv("AGENT_PROJECT_ROOT", Path.cwd()))
        return _load_json(root / ".agentos" / "development-context.json")
    return None


def _development_context(
    project_id: str,
    *,
    context_store: CanonicalContextStore | None = None,
) -> dict[str, Any] | None:
    source = _source_development_context(project_id)
    if context_store is None:
        return source

    runtime = context_store.load(project_id)
    if runtime is not None:
        return runtime
    if source is None:
        return None
    return context_store.seed(
        project_id,
        source,
        seed_revision=str(source.get("updated_at") or "") or None,
    )


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _max_context_age_seconds() -> int:
    raw = os.getenv("AGENTOS_CONTEXT_MAX_AGE_SECONDS", str(DEFAULT_CONTEXT_MAX_AGE_SECONDS))
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_CONTEXT_MAX_AGE_SECONDS
    return value if value >= 60 else DEFAULT_CONTEXT_MAX_AGE_SECONDS


def _freshness(source_updated_at: Any, *, now: datetime | None = None) -> dict[str, Any]:
    compiled = now or datetime.now(timezone.utc)
    if compiled.tzinfo is None:
        compiled = compiled.replace(tzinfo=timezone.utc)
    compiled = compiled.astimezone(timezone.utc)
    max_age = _max_context_age_seconds()
    source_text = str(source_updated_at or "").strip()
    if not source_text:
        return {
            "status": "unknown",
            "source_updated_at": None,
            "compiled_at": _iso(compiled),
            "age_seconds": None,
            "max_age_seconds": max_age,
        }
    try:
        source = datetime.fromisoformat(source_text.replace("Z", "+00:00"))
        if source.tzinfo is None:
            source = source.replace(tzinfo=timezone.utc)
        source = source.astimezone(timezone.utc)
    except ValueError:
        return {
            "status": "unknown",
            "source_updated_at": source_text,
            "compiled_at": _iso(compiled),
            "age_seconds": None,
            "max_age_seconds": max_age,
        }

    raw_age = (compiled - source).total_seconds()
    if raw_age < -300:
        status = "unknown"
        age_seconds = None
    else:
        age_seconds = max(0, int(raw_age))
        status = "fresh" if age_seconds <= max_age else "stale"
    return {
        "status": status,
        "source_updated_at": source_text,
        "compiled_at": _iso(compiled),
        "age_seconds": age_seconds,
        "max_age_seconds": max_age,
    }


def _executor_working_set(
    *,
    project_id: str,
    active_goal: str | None,
    recommended_action: str,
    next_action: str,
    current_findings: list[str],
    next_actions: list[str],
    write_policy: dict[str, Any] | None,
    integration_branch: Any,
    source_revision: Any,
    context_freshness: dict[str, Any],
) -> dict[str, Any]:
    """Compile the semantic minimum needed by a bounded executor."""
    return {
        "schema": WORKING_SET_PROTOCOL,
        "project_id": project_id,
        "active_goal": active_goal,
        "recommended_action": recommended_action,
        "next_action": next_action,
        "current_findings": current_findings,
        "next_actions": next_actions,
        "write_policy": write_policy,
        "integration_branch": integration_branch,
        "source_revision": source_revision,
        "context_freshness": context_freshness,
    }


def compile_execution_context(
    project_id: str,
    state: dict[str, Any],
    *,
    agent: dict[str, Any] | None = None,
    now: datetime | None = None,
    context_store: CanonicalContextStore | None = None,
) -> dict[str, Any]:
    document = _development_context(project_id, context_store=context_store) or {}
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

    current_findings = [str(x) for x in findings[:12]]
    bounded_next_actions = [str(x) for x in next_actions[:8]]
    write_policy = document.get("write_policy") if isinstance(document.get("write_policy"), dict) else None
    integration_branch = active.get("integration_branch") or document.get("integration_branch")
    runtime_meta = document.get("_runtime_context") if isinstance(document.get("_runtime_context"), dict) else None
    source_revision = document.get("updated_at")
    freshness = _freshness(source_revision, now=now)
    active_goal = goal or None
    working_set = _executor_working_set(
        project_id=project_id,
        active_goal=active_goal,
        recommended_action=recommended,
        next_action=next_action,
        current_findings=current_findings,
        next_actions=bounded_next_actions,
        write_policy=write_policy,
        integration_branch=integration_branch,
        source_revision=source_revision,
        context_freshness=freshness,
    )
    return {
        "schema": CONTEXT_PROTOCOL,
        "project_id": project_id,
        "agent": agent or {},
        "active_goal": active_goal,
        "recommended_action": recommended,
        "next_action": next_action,
        "current_findings": current_findings,
        "next_actions": bounded_next_actions,
        "latest_task": latest,
        "current_ir": state.get("currentIR"),
        "continuation": state.get("continuation"),
        "write_policy": write_policy,
        "integration_branch": integration_branch,
        "source_revision": source_revision,
        "context_freshness": freshness,
        "runtime_context": runtime_meta,
        "working_set": working_set,
    }
