#!/usr/bin/env python3
from __future__ import annotations
import argparse
import os
import re
from datetime import datetime, timezone
from pathlib import Path


HOME = Path.home()
PROJECT_ROOT = Path(os.environ.get("AGENTMANAGER_ROOT", os.getcwd() if (Path(os.getcwd()) / ".agent").exists() else HOME / "agentmanager"))
AGENT_DATA_ROOT = Path(os.environ.get("AGENT_DATA_ROOT", HOME / "agent-data"))
DATA_PROJECTS_DIR = AGENT_DATA_ROOT / "projects"
DASHBOARD_PATH = AGENT_DATA_ROOT / "DASHBOARD.md"
WORKSPACE_ROOT = PROJECT_ROOT / "workspace"
LOCAL_STATUS_DIR = PROJECT_ROOT / "projects_status"
PHYSICAL_PROJECTS_ROOT = HOME


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def format_timestamp(ts: datetime | None = None) -> str:
    ts = ts or utc_now()
    return ts.strftime("%Y-%m-%d %H:%M")


def slugify(value: str) -> str:
    lowered = value.strip().lower()
    # Allow underscores for compatibility with existing folders
    slug = re.sub(r"[^a-z0-9_]+", "-", lowered).strip("-")
    return slug or "untitled-project"


def titleize(slug: str) -> str:
    return " ".join(part.capitalize() for part in slug.split("-"))


def ensure_status_file(project_slug: str, display_name: str, status: str, summary: str | None) -> Path:
    project_dir = DATA_PROJECTS_DIR / project_slug
    memory_dir = project_dir / "memory"
    memory_dir.mkdir(parents=True, exist_ok=True)
    status_path = project_dir / "STATUS.md"
    if status_path.exists():
        return status_path

    updated = format_timestamp()
    summary_lines = [
        f"# Project Status: {project_slug}",
        "",
        "## 📍 Summary",
        "| Metric | Value |",
        "| :--- | :--- |",
        f"| **Last Status** | {status} |",
        f"| **Last Updated** | {updated} |",
        "",
        "## 🎯 Current Sprint & Focus",
        "Explain the immediate goal of this project phase here.",
        "",
        "## 📝 Activity Log (Latest on Top)",
        "<!-- LOG_START -->",
        f"- `{updated}` ✅ **REGISTERED**: Project `{display_name}` registered. Follow the 'Mission Brief' to start.",
        "<!-- LOG_END -->",
        "",
        "## 📅 Todo List",
        "- [ ] Define objectives",
        "- [ ] Break work into milestones",
        "- [ ] Execute and report progress",
        "",
        "## 🧠 Working Summary",
        summary or f"{display_name} has been registered and is ready for structured tracking.",
        "",
        "## 🤖 Instructions for AI Agents",
        "- Always read `memory/SHORT_TERM.md` before starting.",
        "- Use `python3 ../../scripts/project_overview.py` for a quick sync.",
        "",
        "## 🛑 Blockers & Issues",
        "- None yet.",
        "",
    ]
    status_path.write_text("\n".join(summary_lines), encoding="utf-8")
    return status_path


def ensure_dashboard_entry(project_slug: str, display_name: str, status: str, type_icon: str):
    DASHBOARD_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not DASHBOARD_PATH.exists():
        DASHBOARD_PATH.write_text(
            "# AI Command Center Dashboard\n\n## Active Projects\n"
            "| Type | Project / Resource Name | Link / Path | Status |\n"
            "| :---: | :--- | :--- | :--- |\n",
            encoding="utf-8",
        )

    content = DASHBOARD_PATH.read_text(encoding="utf-8")
    if f"**{display_name}**" in content or f"./projects/{project_slug}/STATUS.md" in content:
        return

    row = f"| {type_icon} | **{display_name}** | [STATUS](./projects/{project_slug}/STATUS.md) | {status} |"
    lines = content.splitlines()
    insert_idx = None
    for i, line in enumerate(lines):
        if line.startswith("## ") and "Scratchpad" in line:
            insert_idx = i
            break
    if insert_idx is None:
        lines.append(row)
    else:
        lines.insert(insert_idx, row)
    DASHBOARD_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def ensure_local_mounts(project_slug: str, status_path: Path):
    # 1. Physical Source (The actual code repo)
    physical_dir = PHYSICAL_PROJECTS_ROOT / project_slug
    if project_slug != "agentmanager":
        physical_dir.mkdir(parents=True, exist_ok=True)
    
    # 2. Workspace Link (The symlink for developers to access code)
    WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)
    workspace_link = WORKSPACE_ROOT / project_slug
    if not workspace_link.exists() and not workspace_link.is_symlink() and project_slug != "agentmanager":
        workspace_link.symlink_to(physical_dir)

    # 3. Status Dir (The symlink for status tracking)
    local_status_dir = LOCAL_STATUS_DIR / project_slug
    local_status_dir.mkdir(parents=True, exist_ok=True)
    
    local_status = local_status_dir / "STATUS.md"
    local_memory = local_status_dir / "memory"
    data_memory = status_path.parent / "memory"

    if local_status.exists() or local_status.is_symlink():
        local_status.unlink()
    local_status.symlink_to(status_path)

    if local_memory.exists() or local_memory.is_symlink():
        if local_memory.is_symlink() or local_memory.is_file():
            local_memory.unlink()
    if not local_memory.exists():
        local_memory.symlink_to(data_memory)


def register_project(project_name: str, display_name: str | None, status: str, type_icon: str, summary: str | None) -> str:
    project_slug = slugify(project_name)
    pretty_name = display_name.strip() if display_name else titleize(project_slug)
    status_path = ensure_status_file(project_slug, pretty_name, status, summary)
    ensure_dashboard_entry(project_slug, pretty_name, status, type_icon)
    ensure_local_mounts(project_slug, status_path)
    return "\n".join([
        f"Registered project: {pretty_name}",
        f"Slug: {project_slug}",
        f"STATUS: {status_path}",
        f"Workspace: {WORKSPACE_ROOT / project_slug}",
        f"Dashboard: {DASHBOARD_PATH}",
    ])


def main() -> int:
    parser = argparse.ArgumentParser(description="Register a project into the local agent-data layer.")
    parser.add_argument("project_name", help="Project name or slug")
    parser.add_argument("--display-name", dest="display_name", help="Dashboard display name")
    parser.add_argument("--status", default="🆕 Registered", help="Initial project status")
    parser.add_argument("--type-icon", default="🖥️", help="Dashboard type icon")
    parser.add_argument("--summary", help="Initial working summary")
    args = parser.parse_args()

    print(register_project(args.project_name, args.display_name, args.status, args.type_icon, args.summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
