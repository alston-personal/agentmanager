from __future__ import annotations

from pathlib import Path
import re
from typing import Iterable

import yaml

from . import config
from .models import Health, Project, project_from_dict


CATEGORY_TO_SECTOR = {
    "creative": "Creative",
    "product": "Product",
    "infrastructure": "Infrastructure",
    "research": "Research",
    "work": "Work",
    "management": "Management",
}


def _project_dirs() -> Iterable[Path]:
    if not config.PROJECTS_DIR.exists():
        return []
    return sorted(path for path in config.PROJECTS_DIR.iterdir() if path.is_dir())


def load_project(project_dir: Path) -> Project | None:
    yaml_path = project_dir / "project.yaml"
    if not yaml_path.exists():
        return load_legacy_status_project(project_dir)
    try:
        data = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    except OSError:
        return None
    except yaml.YAMLError:
        return None
    if not isinstance(data, dict):
        return None
    return project_from_dict(project_dir.name, data)


def _extract_frontmatter(content: str) -> dict:
    if not content.startswith("---"):
        return {}
    end = content.find("---", 3)
    if end == -1:
        return {}
    try:
        data = yaml.safe_load(content[3:end]) or {}
    except yaml.YAMLError:
        return {}
    return data if isinstance(data, dict) else {}


def _extract_field(content: str, label: str) -> str:
    pattern = rf"\|\s*\*\*{re.escape(label)}\*\*\s*\|\s*([^|]+?)\s*\|"
    match = re.search(pattern, content)
    return match.group(1).strip() if match else ""


def load_legacy_status_project(project_dir: Path) -> Project | None:
    status_path = project_dir / "STATUS.md"
    if not status_path.exists():
        return None
    try:
        content = status_path.read_text(encoding="utf-8")
    except OSError:
        return None

    frontmatter = _extract_frontmatter(content)
    category = str(frontmatter.get("category") or "unknown").lower()
    try:
        priority = int(frontmatter.get("priority", 5))
    except (TypeError, ValueError):
        priority = 5

    return Project(
        project_id=project_dir.name,
        display_name=" ".join(part.capitalize() for part in project_dir.name.split("-")),
        phase=str(frontmatter.get("lifecycle_stage") or "legacy"),
        status=_extract_field(content, "Last Status") or "N/A",
        sector=CATEGORY_TO_SECTOR.get(category, "Legacy"),
        priority=priority,
        actual_code_path=_extract_field(content, "Actual Code Path"),
        data_path=str(project_dir),
        health=Health(freshness="legacy", sync_state="status_md"),
        raw={"source": "STATUS.md"},
    )


def list_projects() -> list[Project]:
    projects: list[Project] = []
    for project_dir in _project_dirs():
        project = load_project(project_dir)
        if project is not None:
            projects.append(project)
    return projects
