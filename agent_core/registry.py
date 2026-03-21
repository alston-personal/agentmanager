"""
agent_core/registry.py
Decorator-based action registry for Agent OS.

Instead of hardcoded if/else in run_workflow.py, every action registers itself:

    @registry.register("status")
    def handle_status(ctx: RuntimeContext) -> ActionResult: ...

The CLI entrypoint then calls:
    registry.dispatch(command_name, ctx)

This makes adding new actions purely additive — no changes to the entrypoint.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from agent_core.context import RuntimeContext
from agent_core.errors import ActionNotFoundError


# ---------------------------------------------------------------------------
# ActionResult: the stable return type all actions must produce
# ---------------------------------------------------------------------------

@dataclass
class ActionResult:
    """
    Standard return type for every action handler.
    The CLI renderer decides how to present this — not the action itself.
    """
    success: bool
    output: str                      # Human-readable output (markdown OK)
    data: dict = field(default_factory=dict)   # Machine-readable payload
    exit_code: int = 0
    warnings: list[str] = field(default_factory=list)

    @classmethod
    def ok(cls, output: str, data: dict = None) -> "ActionResult":
        return cls(success=True, output=output, data=data or {}, exit_code=0)

    @classmethod
    def fail(cls, output: str, exit_code: int = 1, data: dict = None) -> "ActionResult":
        return cls(success=False, output=output, data=data or {}, exit_code=exit_code)


# ---------------------------------------------------------------------------
# ActionMeta: metadata stored alongside each handler
# ---------------------------------------------------------------------------

@dataclass
class ActionMeta:
    name: str
    description: str
    aliases: list[str]
    requires_project: bool


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class ActionRegistry:
    """
    Central registry that maps command names → handler functions.
    Thread-safety is not a concern here (single-process CLI).
    """

    def __init__(self) -> None:
        self._handlers: dict[str, Callable[[RuntimeContext], ActionResult]] = {}
        self._meta: dict[str, ActionMeta] = {}

    def register(
        self,
        name: str,
        description: str = "",
        aliases: list[str] = None,
        requires_project: bool = False,
    ) -> Callable:
        """
        Decorator to register an action handler.

        Usage:
            @registry.register("status", description="Show all project statuses")
            def handle_status(ctx: RuntimeContext) -> ActionResult:
                ...
        """
        def decorator(fn: Callable[[RuntimeContext], ActionResult]) -> Callable:
            meta = ActionMeta(
                name=name,
                description=description,
                aliases=aliases or [],
                requires_project=requires_project,
            )
            self._handlers[name] = fn
            self._meta[name] = meta
            for alias in meta.aliases:
                self._handlers[alias] = fn
            return fn
        return decorator

    def dispatch(self, command: str, ctx: RuntimeContext) -> ActionResult:
        """
        Lookup and call the appropriate action handler.
        Raises ActionNotFoundError if no handler is registered.
        """
        # Normalise: strip leading slash
        command = command.lstrip("/")

        handler = self._handlers.get(command)
        if handler is None:
            raise ActionNotFoundError(command)

        meta = self._meta.get(command) or self._meta.get(
            next((k for k, m in self._meta.items() if command in m.aliases), command), None
        )
        if meta and meta.requires_project:
            ctx.require_project()  # Will raise AgentOSError if missing

        return handler(ctx)

    def list_commands(self) -> list[ActionMeta]:
        """Return metadata for all primary (non-alias) registered commands."""
        return list(self._meta.values())

    def has(self, command: str) -> bool:
        return command.lstrip("/") in self._handlers


# Module-level singleton — import this in action modules and CLI
registry = ActionRegistry()
