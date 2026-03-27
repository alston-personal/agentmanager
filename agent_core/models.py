"""
agent_core/models.py
Dataclasses for structured Agent OS entities.
These are used for reading/writing project.yaml, session.yaml, task.yaml.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime


@dataclass
class ProjectHealth:
    freshness: str = "unknown"       # fresh | stale | unknown
    sync_state: str = "unknown"      # synced | pending_report | diverged
    last_verified_at: Optional[str] = None


@dataclass
class ProjectRecord:
    project_id: str
    display_name: str
    phase: str                        # idea | planning | active | review | maintenance | paused | archived
    status: str
    summary: str = ""
    current_focus: str = ""
    next_action: str = ""
    actual_code_path: str = ""
    data_path: str = ""
    sector: str = "Unknown"           # Infrastructure | Product | Creative | Research
    priority: int = 5                 # 0-10
    tags: list[str] = field(default_factory=list)
    target_workspaces: list[str] = field(default_factory=list)
    assigned_agents: list[str] = field(default_factory=list)
    repo_url: Optional[str] = None
    health: ProjectHealth = field(default_factory=ProjectHealth)
    created_at: str = ""
    updated_at: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> "ProjectRecord":
        health_data = data.get("health") or {}
        health = ProjectHealth(
            freshness=health_data.get("freshness", "unknown"),
            sync_state=health_data.get("sync_state", "unknown"),
            last_verified_at=health_data.get("last_verified_at"),
        )
        return cls(
            project_id=data.get("project_id", ""),
            display_name=data.get("display_name", ""),
            phase=data.get("phase", "active"),
            status=data.get("status", ""),
            summary=data.get("summary", ""),
            current_focus=data.get("current_focus", ""),
            next_action=data.get("next_action", ""),
            actual_code_path=data.get("actual_code_path", ""),
            data_path=data.get("data_path", ""),
            sector=data.get("sector", "Unknown"),
            priority=int(data.get("priority", 5)),
            tags=data.get("tags") or [],
            target_workspaces=data.get("target_workspaces") or [],
            assigned_agents=data.get("assigned_agents") or [],
            repo_url=data.get("repo_url"),
            health=health,
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
        )


@dataclass
class SessionHandover:
    pending_tasks: list[str] = field(default_factory=list)
    next_agent_brief: str = ""
    context_notes: str = ""


@dataclass
class SessionRecord:
    session_id: str
    project_id: str
    agent_id: str
    started_at: str
    status: str = "active"            # active | closed | abandoned | handed_over
    agent_role: str = "engineer"
    entry_mode: str = "manual"
    ended_at: Optional[str] = None
    objective: str = ""
    summary: str = ""
    tasks_started: list[str] = field(default_factory=list)
    tasks_completed: list[str] = field(default_factory=list)
    tasks_blocked: list[str] = field(default_factory=list)
    files_touched: list[str] = field(default_factory=list)
    handover: SessionHandover = field(default_factory=SessionHandover)


@dataclass
class TaskBlocker:
    description: str
    reported_at: str


@dataclass
class TaskRecord:
    task_id: str
    project_id: str
    title: str
    created_at: str
    status: str = "todo"              # todo | in_progress | waiting_human | blocked | done | failed | handed_over | cancelled
    description: str = ""
    priority: int = 5
    sector: str = "Unknown"
    kind: str = "feature"
    assigned_to: Optional[str] = None
    depends_on: list[str] = field(default_factory=list)
    blockers: list[TaskBlocker] = field(default_factory=list)
    acceptance_criteria: list[str] = field(default_factory=list)
    session_id: Optional[str] = None
    updated_at: str = ""
    completed_at: Optional[str] = None


@dataclass
class EventRecord:
    timestamp: str
    event_type: str               # session_started | session_closed | task_updated | project_updated | system_alert
    project_id: str
    actor: str                    # agent_id or 'system'
    session_id: Optional[str] = None
    entity: str = ""              # What entity was affected
    payload: dict = field(default_factory=dict)
