from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any, Iterable

import yaml

from . import config
from .governance_directory import GovernanceEntity, upsert
from .models import Health, Project, project_from_dict


CATEGORY_TO_SECTOR = {
    "creative": "Creative",
    "product": "Product",
    "infrastructure": "Infrastructure",
    "research": "Research",
    "work": "Work",
    "management": "Management",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _project_dirs() -> Iterable[Path]:
    if not config.PROJECTS_DIR.exists():
        return []
    return sorted(path for path in config.PROJECTS_DIR.iterdir() if path.is_dir())


def project_dir(project_id: str) -> Path:
    return config.PROJECTS_DIR / project_id


def project_yaml_path(project_id: str) -> Path:
    return project_dir(project_id) / "project.yaml"


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
    data.setdefault("project_id", project_dir.name)
    data.setdefault("display_name", " ".join(part.capitalize() for part in project_dir.name.split("-")))
    return project_from_dict(project_dir.name, data)


def load_project_document(project_id: str) -> dict[str, Any] | None:
    path = project_yaml_path(project_id)
    if not path.exists():
        return None
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return None
    return data if isinstance(data, dict) else None


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
    for directory in _project_dirs():
        project = load_project(directory)
        if project is not None:
            projects.append(project)
    return projects


@dataclass(frozen=True)
class ProjectSourceAuthority:
    """Canonical source locator, deliberately independent of project identity."""

    repo: str
    branch: str
    canonical_path: str
    node: str

    def validate(self) -> None:
        fields = {
            "repo": self.repo,
            "branch": self.branch,
            "canonical_path": self.canonical_path,
            "node": self.node,
        }
        missing = [key for key, value in fields.items() if not str(value or "").strip()]
        if missing:
            raise ValueError(f"missing project source authority: {', '.join(missing)}")
        if not self.canonical_path.startswith("/"):
            raise ValueError("canonical_path must be absolute")


@dataclass(frozen=True)
class CanonicalProjectRegistration:
    project_id: str
    display_name: str
    source: ProjectSourceAuthority
    state_document: str
    aliases: tuple[str, ...] = ()
    phase: str = "active"
    summary: str = ""
    current_focus: str = ""
    next_action: str = ""

    def validate(self) -> None:
        project_id = self.project_id.strip()
        if not project_id or "/" in project_id or "\\" in project_id:
            raise ValueError("project_id must be a stable slug independent of repo/path identity")
        if not self.display_name.strip():
            raise ValueError("display_name is required")
        self.source.validate()
        if not self.state_document.strip():
            raise ValueError("state_document is required")


def _canonical_document(registration: CanonicalProjectRegistration) -> dict[str, Any]:
    now = _now()
    state_document = registration.state_document
    if not state_document.startswith("/"):
        state_document = str(project_dir(registration.project_id) / state_document)
    return {
        "schema": "agentos.project/v1",
        "project_id": registration.project_id,
        "display_name": registration.display_name,
        "aliases": sorted(set(alias.strip() for alias in registration.aliases if alias.strip())),
        "phase": registration.phase,
        "summary": registration.summary,
        "current_focus": registration.current_focus,
        "next_action": registration.next_action,
        "source": {
            "repo": registration.source.repo,
            "branch": registration.source.branch,
            "canonical_path": registration.source.canonical_path,
            "node": registration.source.node,
        },
        "state": {
            "data_path": str(project_dir(registration.project_id)),
            "document": state_document,
        },
        # Compatibility fields for existing readers. These are projections, not authority.
        "repo_url": f"https://github.com/{registration.source.repo}",
        "actual_code_path": registration.source.canonical_path,
        "data_path": str(project_dir(registration.project_id)),
        "health": {
            "freshness": "fresh",
            "sync_state": "canonical_project_registration",
            "last_verified_at": now,
        },
        "created_at": now,
        "updated_at": now,
    }


def _governance_projection(document: dict[str, Any]) -> GovernanceEntity:
    project_id = str(document["project_id"])
    source = dict(document.get("source") or {})
    state = dict(document.get("state") or {})
    return GovernanceEntity(
        id=f"project://{project_id}",
        kind="project",
        name=str(document.get("display_name") or project_id),
        owns=[f"project-state://{project_id}"],
        provides=[],
        implementation={"source": source},
        authority={
            "exclusive": True,
            "project_identity": True,
            "source_authority": True,
            "state_authority": True,
        },
        state="verified",
        owner="role://governance.keeper",
        metadata={
            "aliases": list(document.get("aliases") or []),
            "state": {
                "document": state.get("document"),
                "data_path": state.get("data_path"),
            },
            "project_store": str(project_yaml_path(project_id)),
            "project_schema": document.get("schema"),
        },
    )


def register_canonical_project(
    registration: CanonicalProjectRegistration,
    *,
    replace: bool = False,
) -> dict[str, Any]:
    """Persist canonical Project Identity and project it into Governance Directory.

    Invariant: Project ID, repository, checkout path, runtime path and deployment target are
    distinct locators. This function never derives source authority from the project slug.
    """

    registration.validate()
    path = project_yaml_path(registration.project_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = load_project_document(registration.project_id)
    if existing is not None and not replace:
        raise ValueError(f"project already registered: {registration.project_id}")

    document = _canonical_document(registration)
    if existing and existing.get("created_at"):
        document["created_at"] = existing["created_at"]

    tmp = path.with_suffix(".tmp")
    tmp.write_text(yaml.safe_dump(document, allow_unicode=True, sort_keys=False), encoding="utf-8")
    tmp.replace(path)

    entity = upsert(_governance_projection(document))
    return {
        "schema": "agentos.project-registration/v1",
        "project_id": registration.project_id,
        "project_store": str(path),
        "governance_entity": entity.id,
        "source": document["source"],
        "state": document["state"],
        "mutation_ready": True,
    }
