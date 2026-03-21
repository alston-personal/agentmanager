#!/usr/bin/env python3
"""
init_project_yaml.py - 批次為已存在的 agent-data 專案生成初始 project.yaml

掃描所有 /home/ubuntu/agent-data/projects/*/STATUS.md
對沒有 project.yaml 的專案，從 STATUS.md 中萃取基本資訊生成初始 yaml。

Usage:
    python3 scripts/init_project_yaml.py
    python3 scripts/init_project_yaml.py --dry-run
    python3 scripts/init_project_yaml.py --project openclaw
"""
import os
import re
import sys
import yaml
import argparse
from pathlib import Path
from datetime import datetime, timezone
from glob import glob


AGENT_DATA_ROOT = Path(os.environ.get("AGENT_DATA_ROOT", "/home/ubuntu/agent-data"))
PROJECTS_DIR = AGENT_DATA_ROOT / "projects"

# 前置 frontmatter 有些 STATUS.md 有 category/priority
CATEGORY_TO_SECTOR = {
    "creative": "Creative",
    "product": "Product",
    "infrastructure": "Infrastructure",
    "research": "Research",
}


def read_file(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def extract_frontmatter(content: str) -> dict:
    """Extract YAML frontmatter from STATUS.md if present."""
    if content.startswith("---"):
        end = content.find("---", 3)
        if end != -1:
            try:
                return yaml.safe_load(content[3:end]) or {}
            except Exception:
                pass
    return {}


def extract_field(content: str, label: str) -> str:
    """Extract a markdown table field by label."""
    pattern = rf"\|\s*\*\*{re.escape(label)}\*\*\s*\|\s*([^|]+?)\s*\|"
    match = re.search(pattern, content)
    return match.group(1).strip() if match else ""


def extract_summary(content: str) -> str:
    """Attempt to extract the Working Summary section."""
    m = re.search(r"## 🧠 Working Summary\s*\n(.*?)(?=\n##|\Z)", content, re.DOTALL)
    if m:
        return m.group(1).strip()[:300]  # Cap at 300 chars
    return ""


def extract_current_focus(content: str) -> str:
    """Extract Current Sprint & Focus section."""
    m = re.search(r"## 🎯 Current Sprint[^#\n]*\n(.*?)(?=\n##|\Z)", content, re.DOTALL)
    if m:
        line = m.group(1).strip().splitlines()[0]  # First line only
        return line[:150]
    return ""


def extract_pending_task(content: str) -> str:
    """Get first pending checkbox item as next_action hint."""
    for line in content.splitlines():
        if line.strip().startswith("- [ ]"):
            return line.strip()[6:]
    return ""


def build_project_yaml(project_slug: str, status_path: Path) -> dict:
    """Build a project.yaml dict from STATUS.md content."""
    content = read_file(status_path)
    fm = extract_frontmatter(content)

    now = datetime.now(timezone.utc).isoformat()
    priority = fm.get("priority", 5)
    category = fm.get("category", "unknown")
    sector = CATEGORY_TO_SECTOR.get(str(category).lower(), "Unknown")

    last_status = extract_field(content, "Last Status") or "🆕 Registered"
    summary = extract_summary(content)
    current_focus = extract_current_focus(content) or "Not defined"
    next_action = extract_pending_task(content) or "Review STATUS.md and define next action."

    return {
        "project_id": project_slug,
        "display_name": " ".join(p.capitalize() for p in project_slug.split("-")),
        "phase": "active",
        "status": last_status,
        "summary": summary or f"{project_slug} project. See STATUS.md for details.",
        "current_focus": current_focus,
        "next_action": next_action,
        "actual_code_path": f"/home/ubuntu/agentmanager/workspace/{project_slug}",
        "data_path": str(PROJECTS_DIR / project_slug),
        "sector": sector,
        "priority": int(priority) if priority else 5,
        "tags": fm.get("tags", []) or [],
        "assigned_agents": [],
        "repo_url": None,
        "health": {
            "freshness": "unknown",
            "sync_state": "pending_report",
            "last_verified_at": now,
        },
        "created_at": now,
        "updated_at": now,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Init project.yaml for all agent-data projects")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be done without writing")
    parser.add_argument("--project", help="Only process this specific project slug")
    parser.add_argument("--force", action="store_true", help="Overwrite existing project.yaml")
    args = parser.parse_args()

    status_paths = sorted(glob(str(PROJECTS_DIR / "*" / "STATUS.md")))

    created = []
    skipped = []
    errors = []

    for status_path_str in status_paths:
        status_path = Path(status_path_str)
        project_slug = status_path.parent.name

        if args.project and project_slug != args.project:
            continue

        yaml_path = status_path.parent / "project.yaml"

        if yaml_path.exists() and not args.force:
            skipped.append(project_slug)
            continue

        try:
            data = build_project_yaml(project_slug, status_path)
            if args.dry_run:
                print(f"\n{'='*50}")
                print(f"[DRY RUN] Would write: {yaml_path}")
                print(yaml.dump(data, allow_unicode=True, default_flow_style=False))
            else:
                with open(yaml_path, "w", encoding="utf-8") as f:
                    yaml.dump(data, f, allow_unicode=True, default_flow_style=False)
                created.append(project_slug)
                print(f"✅ Created: {yaml_path}")
        except Exception as e:
            errors.append((project_slug, str(e)))
            print(f"❌ Error ({project_slug}): {e}", file=sys.stderr)

    print(f"\n--- Summary ---")
    print(f"Created: {len(created)}")
    print(f"Skipped (already exists): {len(skipped)}")
    print(f"Errors: {len(errors)}")
    if skipped:
        print(f"Skipped projects: {', '.join(skipped)}")
    if errors:
        print("Error details:", errors)

    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
