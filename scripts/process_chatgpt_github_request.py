#!/usr/bin/env python3
"""Process one read-only ChatGPT GitHub command against ONE.

The script is intended to run on the ONE host. GitHub is transport only;
canonical state is always read from ONE.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from agentos_node.control_plane_client import ControlPlaneClient
from agentos_node.mcp_read_tools import get_project_state, resolve_active_project, resume_project

PROTOCOL = "agentos.github-command/v1"
RESPONSE_PROTOCOL = "agentos.github-command-response/v1"


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
                "resolution": resolved,
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
            "resolution": resolved,
            "result": resumed,
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
        "result": state,
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
    except Exception as exc:  # fail closed but return machine-readable evidence
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
