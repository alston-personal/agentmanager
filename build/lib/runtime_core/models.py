from enum import Enum
from dataclasses import dataclass, field
from typing import Any, Dict, List
from datetime import datetime

class SessionState(Enum):
    INITIALIZING = "INITIALIZING"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    CLOSING = "CLOSING"
    CLOSED = "CLOSED"
    FAILED = "FAILED"

@dataclass
class CheckpointEvent:
    event_id: str
    session_id: str
    timestamp: datetime
    event_type: str
    payload: Dict[str, Any] = field(default_factory=dict)

@dataclass
class SessionContext:
    project_id: str
    started_at: str
    summary: str
    pending_tasks: List[str]
    blockers: List[str]
    next_steps: List[str]
    branch: str
    uncommitted_files: List[str]
    diff_stat: str
    host_metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class GitMetadata:
    diff_stat: str = ""

@dataclass
class SessionClosePayload:
    session_id: str
    started_at: str
    ended_at: str
    project: str
    summary: str
    files_touched: List[str]
    pending_tasks: List[str]
    blockers: List[str]
    next_steps: List[str]
    branch: str
    uncommitted_files: List[str]
    agent: str
    git: GitMetadata

    def to_dict(self) -> Dict[str, Any]:
        from dataclasses import asdict
        return asdict(self)

