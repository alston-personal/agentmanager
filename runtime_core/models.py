from enum import Enum
from dataclasses import dataclass, field
from typing import Any, Dict
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
