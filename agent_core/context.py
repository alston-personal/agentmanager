"""
agent_core/context.py
Runtime context object passed to every action handler.
Captures: who is running, from which channel, for which project, in which session.
This is what decouples actions from the CLI entrypoint — actions never read sys.argv directly.
"""
from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from agent_core.config import (
    AGENT_DATA_ROOT,
    CENTRAL_PROJECTS_DIR,
    RUNTIME_DIR,
)


@dataclass
class RuntimeContext:
    """
    Immutable snapshot of who is calling what, from where.
    Created once at CLI parse time and passed down to all action handlers.
    """
    # Identity
    agent_id: str = field(default_factory=lambda: os.environ.get("AGENT_ID", "unknown-agent"))
    agent_role: str = field(default_factory=lambda: os.environ.get("AGENT_ROLE", "engineer"))

    # Channel (ide | telegram | cli | api)
    channel: str = field(default_factory=lambda: os.environ.get("AGENT_CHANNEL", "ide"))

    # Session (generated fresh per invocation, or can be injected from env)
    session_id: str = field(default_factory=lambda: os.environ.get(
        "AGENT_SESSION_ID", str(uuid.uuid4())
    ))
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    # Target project (may be None for system-level commands like /status)
    project_id: Optional[str] = field(default_factory=lambda: os.environ.get("AGENT_PROJECT"))

    # Extra args passed from the CLI (after the command name)
    args: list[str] = field(default_factory=list)

    # Flags / options parsed from CLI
    flags: dict = field(default_factory=dict)

    @classmethod
    def from_argv(cls, argv: list[str]) -> "RuntimeContext":
        """
        Factory: parse sys.argv[1:] into a context object.
        argv is everything AFTER the script name and command name.
        e.g. for `run_workflow.py report --project openclaw`
             argv = ["--project", "openclaw"]
        """
        args = []
        flags: dict = {}
        i = 0
        while i < len(argv):
            token = argv[i]
            if token.startswith("--"):
                key = token[2:]
                if i + 1 < len(argv) and not argv[i + 1].startswith("--"):
                    flags[key] = argv[i + 1]
                    i += 2
                else:
                    flags[key] = True
                    i += 1
            else:
                args.append(token)
                i += 1

        project_id = flags.get("project") or os.environ.get("AGENT_PROJECT")

        return cls(
            args=args,
            flags=flags,
            project_id=project_id,
        )

    def require_project(self) -> str:
        """Assert that a project_id is available; raise if missing."""
        from agent_core.errors import AgentOSError
        if not self.project_id:
            raise AgentOSError(
                "This command requires a project context.",
                hint="Use --project <project-id> or set AGENT_PROJECT env var.",
            )
        return self.project_id

    def as_dict(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "agent_role": self.agent_role,
            "channel": self.channel,
            "session_id": self.session_id,
            "started_at": self.started_at,
            "project_id": self.project_id,
        }
