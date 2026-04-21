from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Health:
    freshness: str = "unknown"
    sync_state: str = "unknown"
    last_verified_at: str = ""


@dataclass
class Project:
    project_id: str
    display_name: str
    phase: str = "active"
    status: str = "N/A"
    sector: str = "Unknown"
    priority: int = 5
    repo_url: str | None = None
    actual_code_path: str = ""
    data_path: str = ""
    target_workspaces: list[str] = field(default_factory=list)
    health: Health = field(default_factory=Health)
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def name(self) -> str:
        return self.display_name or self.project_id


def project_from_dict(project_id: str, data: dict[str, Any]) -> Project:
    health_data = data.get("health") or {}
    target_workspaces = data.get("target_workspaces") or []
    if isinstance(target_workspaces, str):
        target_workspaces = [target_workspaces]

    try:
        priority = int(data.get("priority", 5))
    except (TypeError, ValueError):
        priority = 5

    return Project(
        project_id=str(data.get("project_id") or project_id),
        display_name=str(data.get("display_name") or project_id),
        phase=str(data.get("phase") or "active"),
        status=str(data.get("status") or "N/A"),
        sector=str(data.get("sector") or "Unknown"),
        priority=priority,
        repo_url=data.get("repo_url"),
        actual_code_path=str(data.get("actual_code_path") or ""),
        data_path=str(data.get("data_path") or ""),
        target_workspaces=[str(item) for item in target_workspaces],
        health=Health(
            freshness=str(health_data.get("freshness") or "unknown"),
            sync_state=str(health_data.get("sync_state") or "unknown"),
            last_verified_at=str(health_data.get("last_verified_at") or ""),
        ),
        raw=data,
    )

