from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any


SCHEMA = "agentos.executor-inventory/v0.1"
ADOPTION_SCHEMA = "agentos.executor-adoption/v0.1"

_EXECUTORS: tuple[tuple[str, tuple[str, ...], str], ...] = (
    ("claude-code", ("claude",), "claude-code"),
    ("codex", ("codex",), "codex"),
    ("gemini", ("gemini",), "gemini"),
    ("antigravity", ("antigravity",), "antigravity"),
)


def _state_root() -> Path:
    root = os.environ.get("AGENTOS_CLIENT_HOME")
    if root:
        return Path(root)
    return Path.home() / ".agentos"


def _find_binary(candidates: tuple[str, ...]) -> str | None:
    for candidate in candidates:
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    return None


def _probe_version(path: str) -> dict[str, Any]:
    try:
        result = subprocess.run(
            [path, "--version"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "version_probe_ok": False,
            "version": None,
            "probe_error": type(exc).__name__,
        }

    text = (result.stdout or result.stderr or "").strip()
    first_line = text.splitlines()[0][:300] if text else None
    return {
        "version_probe_ok": result.returncode == 0,
        "version": first_line,
        "probe_returncode": result.returncode,
    }


def _bridge_state(provider: str) -> dict[str, Any]:
    try:
        from agentos_node.session_bridge import describe_bridge

        descriptor = describe_bridge(provider)
    except Exception as exc:
        return {
            "bridge_ready": False,
            "bridge_error": type(exc).__name__,
            "bridge_capabilities": [],
        }

    if not isinstance(descriptor, dict):
        return {
            "bridge_ready": False,
            "bridge_error": "invalid_descriptor",
            "bridge_capabilities": [],
        }

    return {
        "bridge_ready": bool(descriptor.get("ready")),
        "bridge_capabilities": sorted(
            {
                str(item).strip()
                for item in (descriptor.get("capabilities") or [])
                if str(item).strip()
            }
        ),
    }


def discover_executor_inventory() -> dict[str, Any]:
    executors: list[dict[str, Any]] = []

    for executor_id, candidates, bridge_provider in _EXECUTORS:
        path = _find_binary(candidates)
        bridge = _bridge_state(bridge_provider)

        item: dict[str, Any] = {
            "executor_id": executor_id,
            "detected": bool(path),
            "binary": Path(path).name if path else None,
            "bridge_ready": bool(bridge.get("bridge_ready")),
            "bridge_capabilities": list(bridge.get("bridge_capabilities") or []),
        }

        if path:
            item.update(_probe_version(path))

        if item["bridge_ready"]:
            item["state"] = "READY"
            item["adoptable"] = True
            item["routable"] = True
        elif path:
            item["state"] = "DISCOVERED"
            item["adoptable"] = True
            item["routable"] = False
        else:
            item["state"] = "UNAVAILABLE"
            item["adoptable"] = False
            item["routable"] = False

        executors.append(item)

    return {
        "schema": SCHEMA,
        "executors": executors,
    }


def reconcile_executor_adoption(*, state_root: str | Path | None = None) -> dict[str, Any]:
    root = Path(state_root) if state_root is not None else _state_root()
    root.mkdir(parents=True, exist_ok=True)

    inventory = discover_executor_inventory()
    adopted = [
        {
            "executor_id": item["executor_id"],
            "state": item["state"],
            "adopted": bool(item.get("adoptable")),
            "routable": bool(item.get("routable")),
            "bridge_capabilities": list(item.get("bridge_capabilities") or []),
            "version": item.get("version"),
        }
        for item in inventory["executors"]
    ]

    payload = {
        "schema": ADOPTION_SCHEMA,
        "inventory_schema": inventory["schema"],
        "executors": adopted,
        "summary": {
            "ready": sum(1 for item in adopted if item["state"] == "READY"),
            "discovered": sum(1 for item in adopted if item["state"] == "DISCOVERED"),
            "unavailable": sum(1 for item in adopted if item["state"] == "UNAVAILABLE"),
        },
    }

    target = root / "executor-adoption.json"
    fd, temp_name = tempfile.mkstemp(prefix=".executor-adoption-", suffix=".json", dir=str(root))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temp_name, target)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)

    return {
        "executor_adoption": payload,
        "state_path": str(target),
        "ok": True,
    }
