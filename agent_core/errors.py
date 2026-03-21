"""
agent_core/errors.py
Unified exception hierarchy for Agent OS.
All user-facing errors should inherit from AgentOSError so the CLI
can render them with a consistent format.
"""


class AgentOSError(Exception):
    """Base class for all Agent OS errors."""
    exit_code: int = 1

    def __init__(self, message: str, hint: str = ""):
        super().__init__(message)
        self.message = message
        self.hint = hint

    def __str__(self) -> str:
        base = f"❌ {self.message}"
        if self.hint:
            base += f"\n   💡 {self.hint}"
        return base


class ProjectNotFoundError(AgentOSError):
    """Raised when a project cannot be located in agent-data."""
    exit_code = 2

    def __init__(self, project_id: str):
        super().__init__(
            message=f"Project '{project_id}' not found in agent-data.",
            hint="Run `/register-project` or check AGENT_DATA_ROOT.",
        )
        self.project_id = project_id


class SchemaValidationError(AgentOSError):
    """Raised when a YAML/JSON file fails schema validation."""
    exit_code = 3


class WorkflowNotFoundError(AgentOSError):
    """Raised when a requested workflow cannot be located."""
    exit_code = 4

    def __init__(self, name: str):
        super().__init__(
            message=f"Workflow '/{name}' not found.",
            hint="Run `list` to see available workflows.",
        )


class ActionNotFoundError(AgentOSError):
    """Raised when the registry has no handler for a command."""
    exit_code = 5

    def __init__(self, name: str):
        super().__init__(
            message=f"No registered action for command '/{name}'.",
            hint="Check `agent_core/registry.py` for registered actions.",
        )


class SessionError(AgentOSError):
    """Raised for session lifecycle problems."""
    exit_code = 6


class SharedMemoryError(AgentOSError):
    """Raised when the LCS shared memory bus cannot be read/written."""
    exit_code = 7
