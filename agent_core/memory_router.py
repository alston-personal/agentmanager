from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import config


_PROJECT_ROOT_PRIORITY_ENV_VARS = (
    "AGENT_CONTEXT_PROJECT_ROOT",
    "CLAUDE_PROJECT_DIR",
    "AGENT_ACTIVE_PROJECT_ROOT",
)


def _expand(path: str | Path) -> Path:
    return Path(path).expanduser().resolve()


def _path_from_env(name: str) -> Path | None:
    value = os.environ.get(name)
    if not value:
        return None
    return _expand(value)


def _looks_like_project_root(path: Path) -> bool:
    if not path.exists() or not path.is_dir():
        return False
    markers = [
        path / "STATUS.md",
        path / "memory",
        path / "project.yaml",
        path / ".agent",
    ]
    return any(marker.exists() for marker in markers)


def _discover_project_root(start: Path | None = None) -> Path:
    start = _expand(start or Path.cwd())
    for candidate in (start, *start.parents):
        if _looks_like_project_root(candidate):
            return candidate
    return _expand(config.PROJECT_ROOT)


def resolve_project_root(project_root: str | Path | None = None, cwd: str | Path | None = None) -> Path:
    if project_root:
        return _expand(project_root)
    for env_name in _PROJECT_ROOT_PRIORITY_ENV_VARS:
        env_path = _path_from_env(env_name)
        if env_path:
            return env_path
    discovered = _discover_project_root(_expand(cwd) if cwd else None)
    if discovered != _expand(config.PROJECT_ROOT):
        return discovered
    project_root_env = _path_from_env("AGENT_PROJECT_ROOT")
    if project_root_env:
        return project_root_env
    return discovered


def resolve_data_root(data_root: str | Path | None = None) -> Path:
    if data_root:
        return _expand(data_root)
    env_root = os.environ.get("AGENT_DATA_ROOT") or os.environ.get("AGENT_DATA_DIR")
    if env_root:
        return _expand(env_root)
    return _expand(config.AGENT_DATA_ROOT)


@dataclass(slots=True)
class MemoryRoute:
    project_root: Path
    data_root: Path
    project_name: str
    project_data_root: Path
    memory_dir: Path
    status_path: Path
    short_term_path: Path
    long_term_path: Path
    session_sync_path: Path
    transcripts_dir: Path
    telegram_sessions_dir: Path
    runtime_dir: Path
    logs_dir: Path
    source: str = "discovered"

    def ensure_dirs(self) -> None:
        self.project_data_root.mkdir(parents=True, exist_ok=True)
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self.session_sync_path.parent.mkdir(parents=True, exist_ok=True)
        self.transcripts_dir.mkdir(parents=True, exist_ok=True)
        self.telegram_sessions_dir.mkdir(parents=True, exist_ok=True)
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)

    def as_dict(self) -> dict[str, Any]:
        return {
            "project_root": str(self.project_root),
            "data_root": str(self.data_root),
            "project_name": self.project_name,
            "project_data_root": str(self.project_data_root),
            "memory_dir": str(self.memory_dir),
            "status_path": str(self.status_path),
            "short_term_path": str(self.short_term_path),
            "long_term_path": str(self.long_term_path),
            "session_sync_path": str(self.session_sync_path),
            "transcripts_dir": str(self.transcripts_dir),
            "telegram_sessions_dir": str(self.telegram_sessions_dir),
            "runtime_dir": str(self.runtime_dir),
            "logs_dir": str(self.logs_dir),
            "source": self.source,
        }


def _route_from_paths(project_root: Path, data_root: Path, source: str) -> MemoryRoute:
    project_name = project_root.name
    project_data_root = data_root / "projects" / project_name
    memory_dir = project_data_root / "memory"
    return MemoryRoute(
        project_root=project_root,
        data_root=data_root,
        project_name=project_name,
        project_data_root=project_data_root,
        memory_dir=memory_dir,
        status_path=project_data_root / "STATUS.md",
        short_term_path=memory_dir / "SHORT_TERM.md",
        long_term_path=memory_dir / "LONG_TERM.md",
        session_sync_path=data_root / "memory" / "session_sync.md",
        transcripts_dir=data_root / "memory" / "telegram_sessions",
        telegram_sessions_dir=data_root / "memory" / "telegram_sessions",
        runtime_dir=data_root / "runtime",
        logs_dir=data_root / "logs",
        source=source,
    )


def resolve_memory_route(
    project_root: str | Path | None = None,
    data_root: str | Path | None = None,
    cwd: str | Path | None = None,
) -> MemoryRoute:
    resolved_project_root = resolve_project_root(project_root=project_root, cwd=cwd)
    resolved_data_root = resolve_data_root(data_root=data_root)
    source = "explicit" if project_root or data_root else "discovered"
    route = _route_from_paths(resolved_project_root, resolved_data_root, source)
    route.ensure_dirs()
    return route
