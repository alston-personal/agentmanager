#!/usr/bin/env python3
"""Process one read-only ChatGPT GitHub command against ONE.

GitHub is transport only. Canonical state remains in ONE, and only an explicit
continuity-safe allowlist may cross the GitHub transport boundary.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from agentos_node.control_plane_client import ControlPlaneClient
from agentos_node.mcp_read_tools import get_project_state, resolve_active_project, resume_project

PROTOCOL = "agentos.github-command/v1"
RESPONSE_PROTOCOL = "agentos.github-command-response/v1"


def _pick(source: dict[str, Any], *keys: str) -> dict[str, Any]:
    return {key: source.get(key) for key in keys if key in source}


def _safe_ir(raw: object) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    return _pick(
        raw,
        "schema_version",
        "ir_id",
        "parent_ir_id",
        "project_id",
        "goal",
        "capability",
        "constraints",
        "decisions",
        "pending_tasks",
        "continuation",
        "hop_count",
        "created_at",
    )


def _safe_task(raw: object) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    return _pick(raw, "taskId", "projectId", "status", "capability", "targetNodeId", "createdAt", "updatedAt")


def _safe_resolution(raw: object) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    safe = _pick(raw, "protocol", "resolution", "project_id")
    selected = raw.get("selected")
    if isinstance(selected, dict):
        safe["selected"] = _pick(
            selected,
            "project_id",
            "goal",
            "recommended_action",
            "current_source",
            "last_active_at",
            "hint_score",
        )
    candidates = raw.get("candidates")
    if isinstance(candidates, list):
        safe["candidates"] = [
            _pick(
                item,
                "project_id",
                "goal",
                "recommended_action",
                "current_source",
                "last_active_at",
                "hint_score",
            )
            for item in candidates[:5]
            if isinstance(item, dict)
        ]
    return safe


def _safe_execution_context(raw: object) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    safe = _pick(
        raw,
        "schema",
        "project_id",
        "active_goal",
        "recommended_action",
        "next_action",
        "next_actions",
        "current_findings",
        "integration_branch",
        "source_revision",
        "write_policy",
        "context_freshness",
    )
    safe_ir = _safe_ir(raw.get("current_ir"))
    if safe_ir is not None:
        safe["current_ir"] = safe_ir
    safe_task = _safe_task(raw.get("latest_task"))
    if safe_task is not None:
        safe["latest_task"] = safe_task
    agent = raw.get("agent")
    if isinstance(agent, dict):
        safe["agent"] = _pick(agent, "identity_scope", "kind", "principal_id", "runtime_id", "transport")
    return safe


def _safe_resume(raw: object) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    safe = _pick(
        raw,
        "protocol",
        "runtime_id",
        "project_id",
        "session_id",
        "recommended_action",
        "current_source",
        "latest_task_id",
        "current_ir_id",
        "current_ir_digest",
    )
    context = _safe_execution_context(raw.get("execution_context"))
    if context is not None:
        safe["execution_context"] = context
    return safe


def _safe_project_state(raw: object) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    safe = _pick(raw, "protocol", "projectId", "recommendedAction", "currentSource")
    ir = _safe_ir(raw.get("currentIR"))
    if ir is not None:
        safe["currentIR"] = ir
    task = _safe_task(raw.get("latestTask"))
    if task is not None:
        safe["latestTask"] = task
    return safe


def _load_request(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("protocol") != PROTOCOL:
        raise ValueError("unsupported protocol")
    request_id = str(payload.get("request_id") or "").strip()
    if not request_id or "/" in request_id or ".." in request_id:
        raise ValueError("invalid request_id")
    if path.stem != request_id:
        raise ValueError("request filename must match request_id")
    action = str(payload.get("action") or "").strip()
    if action not in {"resume", "project_state"}:
        raise ValueError("unsupported action")
    return payload


def _client() -> ControlPlaneClient:
    url = os.environ.get("AGENTOS_CONTROL_PLANE_URL", "http://127.0.0.1:8765").strip()
    token = os.environ.get("AGENTOS_CONTROL_PLANE_TOKEN", "").strip()
    if not token:
        raise RuntimeError("AGENTOS_CONTROL_PLANE_TOKEN is required")
    return ControlPlaneClient(url, token=token)


def process(payload: dict) -> dict:
    client = _client()
    action = payload["action"]
    request_id = payload["request_id"]

    if action == "resume":
        hint = str(payload.get("hint") or "").strip() or None
        resolved = resolve_active_project(client, hint=hint)
        if resolved.get("resolution") != "resolved" or not resolved.get("project_id"):
            return {
                "protocol": RESPONSE_PROTOCOL,
                "request_id": request_id,
                "ok": False,
                "action": action,
                "error": "active_project_not_resolved",
                "resolution": _safe_resolution(resolved),
            }
        project_id = str(resolved["project_id"])
        resumed = resume_project(
            client,
            project_id,
            runtime_id="chatgpt-github",
            principal_id="chatgpt-github",
            transport="github",
        )
        return {
            "protocol": RESPONSE_PROTOCOL,
            "request_id": request_id,
            "ok": True,
            "action": action,
            "project_id": project_id,
            "resolution": _safe_resolution(resolved),
            "result": _safe_resume(resumed),
        }

    project_id = str(payload.get("project_id") or "").strip()
    if not project_id:
        raise ValueError("project_id is required for project_state")
    state = get_project_state(client, project_id)
    return {
        "protocol": RESPONSE_PROTOCOL,
        "request_id": request_id,
        "ok": True,
        "action": action,
        "project_id": project_id,
        "result": _safe_project_state(state),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("request")
    args = parser.parse_args()
    request_path = Path(args.request)
    request_id = request_path.stem
    try:
        payload = _load_request(request_path)
        response = process(payload)
    except Exception as exc:
        response = {
            "protocol": RESPONSE_PROTOCOL,
            "request_id": request_id,
            "ok": False,
            "error": type(exc).__name__,
            "message": str(exc),
        }
    json.dump(response, sys.stdout, ensure_ascii=False, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if response.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
