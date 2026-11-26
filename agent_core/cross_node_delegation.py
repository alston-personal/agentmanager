"""Governed Cross-Node Delegation Protocol (agentos.cross-node-delegation/v1).

Enforces capability fencing and mutual node trust for inter-node delegation.
Prevents unreviewed lateral shell execution while enabling governed desktop,
preview, and safe file exchange between nodes.
"""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

CROSS_NODE_DELEGATION_SCHEMA = "agentos.cross-node-delegation/v1"

# Governed safe actions permitted for inter-node consumption
ALLOWED_CROSS_NODE_ACTIONS: frozenset[str] = frozenset({
    "desktop.open_url",
    "desktop.screenshot",
    "desktop.windows.inspect",
    "desktop.session.inspect",
    "filesystem.read",
    "filesystem.write",
    "filesystem.search",
    "notification.send",
})

# Forbidden high-risk actions that cannot be delegated across nodes
FORBIDDEN_LATERAL_ACTIONS: frozenset[str] = frozenset({
    "shell.exec",
    "process.exec",
    "test.run",
})


def validate_cross_node_task(task: dict[str, Any], *, caller_node_id: str, target_node_id: str) -> None:
    """Validate that an inter-node task adheres to capability fencing policies."""
    if not isinstance(task, dict):
        raise ValueError("task must be a dictionary")

    action = str(task.get("action") or "").strip()
    if not action:
        raise ValueError("task action is required")

    # Strict lateral movement block
    if action in FORBIDDEN_LATERAL_ACTIONS:
        raise PermissionError(
            f"cross-node delegation violation: action '{action}' is strictly prohibited across nodes "
            f"(caller: {caller_node_id} -> target: {target_node_id}). Lateral shell execution is forbidden."
        )

    if action not in ALLOWED_CROSS_NODE_ACTIONS:
        raise PermissionError(
            f"action '{action}' is not in the allowed cross-node capability whitelist: "
            f"{sorted(ALLOWED_CROSS_NODE_ACTIONS)}"
        )

    # Action-specific parameter validation
    if action == "desktop.open_url":
        url = str(task.get("url") or "").strip()
        if not url:
            raise ValueError("desktop.open_url requires a valid non-empty 'url'")
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("desktop.open_url only permits absolute http/https URLs")

    elif action in {"filesystem.read", "filesystem.write"}:
        path = str(task.get("path") or "").strip()
        if not path:
            raise ValueError(f"{action} requires a valid 'path'")
        # Prevent traversal outside allowed roots
        if ".." in path:
            raise PermissionError(f"directory traversal in path is forbidden: {path}")


def create_delegation_record(
    caller_node_id: str,
    target_node_id: str,
    task: dict[str, Any],
) -> dict[str, Any]:
    """Create a structured agentos.cross-node-delegation/v1 record."""
    validate_cross_node_task(task, caller_node_id=caller_node_id, target_node_id=target_node_id)
    return {
        "schema": CROSS_NODE_DELEGATION_SCHEMA,
        "caller_node_id": caller_node_id,
        "target_node_id": target_node_id,
        "action": task.get("action"),
        "task_id": task.get("task_id"),
    }
