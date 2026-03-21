"""
agent_core/project_store.py
Read/write project.yaml and related per-project data from agent-data layer.
This is the canonical source of truth — no more regex parsing markdown.
"""
from __future__ import annotations

import json
import yaml
from pathlib import Path
from typing import Optional
from glob import glob

from agent_core.config import CENTRAL_PROJECTS_DIR, EVENTS_JSONL_NAME
from agent_core.models import ProjectRecord, EventRecord


def load_project(project_id: str) -> Optional[ProjectRecord]:
    """Load a single project.yaml → ProjectRecord. Returns None if not found."""
    yaml_path = CENTRAL_PROJECTS_DIR / project_id / "project.yaml"
    if not yaml_path.exists():
        return None
    try:
        data = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
        return ProjectRecord.from_dict(data)
    except Exception as e:
        raise RuntimeError(f"Failed to load project.yaml for {project_id}: {e}") from e


def save_project(record: ProjectRecord) -> None:
    """Persist a ProjectRecord back to project.yaml."""
    import dataclasses
    project_dir = CENTRAL_PROJECTS_DIR / record.project_id
    project_dir.mkdir(parents=True, exist_ok=True)
    yaml_path = project_dir / "project.yaml"

    data = dataclasses.asdict(record)
    with open(yaml_path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False)


def list_projects(sector: str | None = None, phase: str | None = None) -> list[ProjectRecord]:
    """List all projects, optionally filtered by sector or phase."""
    yaml_paths = sorted(glob(str(CENTRAL_PROJECTS_DIR / "*" / "project.yaml")))
    results = []
    for path_str in yaml_paths:
        try:
            data = yaml.safe_load(Path(path_str).read_text(encoding="utf-8")) or {}
            record = ProjectRecord.from_dict(data)
            if sector and record.sector != sector:
                continue
            if phase and record.phase != phase:
                continue
            results.append(record)
        except Exception:
            pass  # Skip malformed yaml silently
    return results


def emit_event(event: EventRecord) -> None:
    """Append an event to the per-project persistent events.jsonl."""
    import dataclasses
    project_dir = CENTRAL_PROJECTS_DIR / event.project_id
    project_dir.mkdir(parents=True, exist_ok=True)
    events_path = project_dir / EVENTS_JSONL_NAME

    record_dict = dataclasses.asdict(event)
    with open(events_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record_dict, ensure_ascii=False) + "\n")
