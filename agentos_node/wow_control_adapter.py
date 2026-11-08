"""Opt-in read-only WoW control surface for an existing interactive Node.

No addon transport, command execution, network listener, privilege grant, or
new Node identity is supplied here. Live state is owned by the injected reader.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

CAPABILITY = "wow.control.status"


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
        result = self._reader()
        if not isinstance(result, dict):
            raise ValueError("status reader must return an object")
        # Reader must be trusted Node-side; never echo caller-supplied contents.
        return {"status": "OK", "snapshot": result}


def create_adapter() -> WoWControlAdapter:
    """Explicit opt-in via existing AGENTOS_NODE_ADAPTERS; unbound by default."""
    return WoWControlAdapter()
