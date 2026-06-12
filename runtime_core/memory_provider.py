from typing import Any, Dict, List
from runtime_core.interfaces import ContextProviderInterface
from runtime_core.models import SessionContext, SessionClosePayload

class InMemoryContextProvider(ContextProviderInterface):
    """
    An in-memory ContextProvider implementation for testing and non-AgentOS environments.
    """
    def __init__(
        self,
        project_id: str = "test-project",
        started_at: str = "2026-06-12T12:00:00Z",
        summary: str = "In-memory session",
        pending_tasks: List[str] = None,
        blockers: List[str] = None,
        next_steps: List[str] = None,
        branch: str = "main",
        uncommitted_files: List[str] = None,
        diff_stat: str = "1 file changed, 1 insertion(+)",
        host_metadata: Dict[str, Any] = None
    ):
        self.project_id = project_id
        self.started_at = started_at
        self.summary = summary
        self.pending_tasks = pending_tasks or []
        self.blockers = blockers or []
        self.next_steps = next_steps or []
        self.branch = branch
        self.uncommitted_files = uncommitted_files or []
        self.diff_stat = diff_stat
        self.host_metadata = host_metadata or {}
        
        # In-memory storage for closed sessions
        self.closed_sessions: List[SessionClosePayload] = []

    def load_context(self) -> SessionContext:
        return SessionContext(
            project_id=self.project_id,
            started_at=self.started_at,
            summary=self.summary,
            pending_tasks=self.pending_tasks,
            blockers=self.blockers,
            next_steps=self.next_steps,
            branch=self.branch,
            uncommitted_files=self.uncommitted_files,
            diff_stat=self.diff_stat,
            host_metadata=self.host_metadata
        )

    def persist_session_close(self, payload: SessionClosePayload) -> tuple[str, str]:
        self.closed_sessions.append(payload)
        record_uri = f"memory://sessions/{payload.session_id}"
        compact_entry = f"InMemory Session {payload.session_id} Closed. Summary: {payload.summary}"
        return record_uri, compact_entry
