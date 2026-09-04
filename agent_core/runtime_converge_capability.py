from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


MARKER_SCHEMA = "agentos.action-relay-capabilities/v1"
MARKER_ACTION = "agentos.runtime.converge"
NODE_CAPABILITY = "node.runtime.converge"
ALLOWED_SOURCE_REF = "core/integration"
DEFAULT_MARKER = Path("/home/ubuntu/agent-data/runtime/action-relay/capabilities.json")
EXPECTED_ACTIONS = {"agentos.executor.job", MARKER_ACTION}
EXPECTED_NODE_CAPABILITIES = {NODE_CAPABILITY}


def validate_installed_marker(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    if payload.get("schema") != MARKER_SCHEMA:
        return None
    if payload.get("source_ref") != ALLOWED_SOURCE_REF:
        return None
    source_commit = str(payload.get("source_commit") or "")
    if not re.fullmatch(r"[0-9a-f]{40}", source_commit):
        return None

    actions = payload.get("actions")
    capabilities = payload.get("node_capabilities")
    if not isinstance(actions, list) or set(actions) != EXPECTED_ACTIONS:
        return None
    if not isinstance(capabilities, list) or set(capabilities) != EXPECTED_NODE_CAPABILITIES:
        return None
    return {
        "source_ref": ALLOWED_SOURCE_REF,
        "source_commit": source_commit,
        "actions": sorted(EXPECTED_ACTIONS),
        "node_capabilities": sorted(EXPECTED_NODE_CAPABILITIES),
    }


def installed_core_capabilities(marker_path: str | Path = DEFAULT_MARKER) -> list[str]:
    path = Path(marker_path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        return []
    marker = validate_installed_marker(payload)
    if marker is None:
        return []
    return list(marker["node_capabilities"])
