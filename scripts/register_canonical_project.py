#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from agent_core import config
from agent_core.project_store import (
    CanonicalProjectRegistration,
    ProjectSourceAuthority,
    register_canonical_project,
)


def ensure_status(project_id: str, display_name: str, summary: str, current_focus: str, next_action: str) -> Path:
    project_dir = config.PROJECTS_DIR / project_id
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "memory").mkdir(parents=True, exist_ok=True)
    status = project_dir / "STATUS.md"
    if not status.exists():
        status.write_text(
            "\n".join(
                [
                    f"# Project Status: {display_name}",
                    "",
                    "## Summary",
                    summary,
                    "",
                    "## Current Focus",
                    current_focus,
                    "",
                    "## Next Action",
                    next_action,
                    "",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
    return status


def ensure_dashboard(project_id: str, display_name: str) -> Path:
    dashboard = config.AGENT_DATA_ROOT / "DASHBOARD.md"
    dashboard.parent.mkdir(parents=True, exist_ok=True)
    marker = f"./projects/{project_id}/STATUS.md"
    if dashboard.exists():
        content = dashboard.read_text(encoding="utf-8")
    else:
        content = "# AI Command Center Dashboard\n\n## Active Projects\n\n"
    if marker not in content:
        if not content.endswith("\n"):
            content += "\n"
        content += f"- **{display_name}** — [STATUS]({marker})\n"
        dashboard.write_text(content, encoding="utf-8")
    return dashboard


def main() -> int:
    parser = argparse.ArgumentParser(description="Register a canonical AgentOS project.")
    parser.add_argument("project_id")
    parser.add_argument("--display-name", required=True)
    parser.add_argument("--repo", required=True, help="GitHub owner/repo source authority")
    parser.add_argument("--branch", default="main")
    parser.add_argument("--canonical-path", required=True)
    parser.add_argument("--node", required=True)
    parser.add_argument("--alias", action="append", default=[])
    parser.add_argument("--summary", default="")
    parser.add_argument("--current-focus", default="")
    parser.add_argument("--next-action", default="")
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()

    status = ensure_status(
        args.project_id,
        args.display_name,
        args.summary,
        args.current_focus,
        args.next_action,
    )
    dashboard = ensure_dashboard(args.project_id, args.display_name)
    result = register_canonical_project(
        CanonicalProjectRegistration(
            project_id=args.project_id,
            display_name=args.display_name,
            aliases=tuple(args.alias),
            source=ProjectSourceAuthority(
                repo=args.repo,
                branch=args.branch,
                canonical_path=args.canonical_path,
                node=args.node,
            ),
            state_document=str(status),
            summary=args.summary,
            current_focus=args.current_focus,
            next_action=args.next_action,
        ),
        replace=args.replace,
    )
    result["dashboard"] = str(dashboard)
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
