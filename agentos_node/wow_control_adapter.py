"""Opt-in read-only WoW control surface for an existing interactive Node.

No addon transport, command execution, network listener, privilege grant, or
new Node identity is supplied here. Live state is owned by the injected reader.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

CAPABILITY = "wow.control.status"
# Only this minimal display projection may cross the game/Bridge boundary.
_ALLOWED_FIELDS = frozenset({"state", "paw", "receipt"})
_SAFE_LABEL = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_SAFE_RECEIPT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


def _safe_snapshot(value: Any) -> dict[str, str | None]:
    """Fail closed on unknown, nested, oversized, or non-display data."""
    if not isinstance(value, dict) or not value or set(value) - _ALLOWED_FIELDS:
        raise ValueError("unsafe WoW status snapshot schema")
    result: dict[str, str | None] = {}
    for key, field in value.items():
        if key == "receipt" and field is None:
            result[key] = None
            continue
        pattern = _SAFE_RECEIPT if key == "receipt" else _SAFE_LABEL
        if not isinstance(field, str) or not pattern.fullmatch(field):
            raise ValueError("unsafe WoW status snapshot field")
        result[key] = field
    return result


class WoWControlAdapter:
    adapter_id = "wow-control"

    def __init__(self, status_reader: Callable[[], dict[str, Any]] | None = None):
        self._reader = status_reader

    def capabilities(self) -> tuple[str, ...]:
        return (CAPABILITY,)

    def describe(self) -> dict[str, Any]:
        return {
            "kind": "interactive-session",
            "transport": "not-configured",
            "live_verified": False,
            "read_only": True,
            "implementation": "candidate",
        }

    def execute(self, task: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(task, dict):
            raise ValueError("task must be an object")
        if task.get("action") != CAPABILITY:
            raise ValueError("unsupported WoW control action")
        if set(task) != {"action"}:
            raise ValueError("WoW status takes no caller-controlled arguments")
        if self._reader is None:
            return {"status": "UNAVAILABLE", "reason": "RUNTIME_READER_NOT_BOUND"}
        return {"status": "OK", "snapshot": _safe_snapshot(self._reader())}


def create_adapter() -> WoWControlAdapter:
    """Explicit opt-in via existing AGENTOS_NODE_ADAPTERS; unbound by default."""
    return WoWControlAdapter()
