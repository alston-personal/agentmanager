#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(os.environ.get("AGENTMANAGER_ROOT", os.getcwd() if (Path(os.getcwd()) / ".agent").exists() else "/home/ubuntu/agentmanager"))
AGENT_DATA_ROOT = Path(os.environ.get("AGENT_DATA_ROOT", "/home/ubuntu/agent-data"))
SPECS_DIR = AGENT_DATA_ROOT / "specs"
REPORT_DIR = AGENT_DATA_ROOT / "journals" / "spec_governance"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover - optional dependency fallback
    yaml = None

try:
    from agent_core.project_store import list_projects
except Exception:  # pragma: no cover - fallback when project store unavailable
    list_projects = None


@dataclass
class SpecFinding:
    spec: str
    title: str
    status: str
    owner: str
    targets: list[str]
    required_capabilities: list[str]
    open_items: int
    freshness_days: int
    notes: list[str]


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def parse_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    if not content.startswith("---"):
        return {}, content

    lines = content.splitlines()
    if len(lines) < 3:
        return {}, content

    end_idx = None
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            end_idx = idx
            break
    if end_idx is None:
        return {}, content

    raw_meta = "\n".join(lines[1:end_idx])
    body = "\n".join(lines[end_idx + 1 :])
    if yaml is None:
        return {}, body
    try:
        meta = yaml.safe_load(raw_meta) or {}
        if not isinstance(meta, dict):
            meta = {}
        return meta, body
    except Exception:
        return {}, body


def first_heading(text: str) -> str:
    for line in text.splitlines():
        if line.startswith("#"):
            return line.lstrip("#").strip()
    return "Untitled Spec"


def normalize_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()]


def count_open_checkboxes(text: str) -> int:
    return len(re.findall(r"^\s*-\s+\[ \]\s+", text, flags=re.MULTILINE))


def load_projects_by_id() -> dict[str, Any]:
    projects: dict[str, Any] = {}
    if list_projects is None:
        return projects
    try:
        for project in list_projects():
            project_id = getattr(project, "project_id", None) or getattr(project, "name", None)
            if project_id:
                projects[str(project_id)] = project
    except Exception:
        return {}
    return projects


def project_capabilities(project: Any) -> tuple[list[str], list[str]]:
    provided = list(getattr(project, "capabilities_provided", []) or [])
    required = list(getattr(project, "capabilities_required", []) or [])
    return provided, required


def provider_map(projects: dict[str, Any]) -> dict[str, list[str]]:
    mapping: dict[str, list[str]] = {}
    for project_id, project in projects.items():
        provided, _ = project_capabilities(project)
        for capability in provided:
            mapping.setdefault(capability, []).append(project_id)
    return mapping


def build_findings(limit_spec: str | None = None) -> list[SpecFinding]:
    projects = load_projects_by_id()
    providers = provider_map(projects)
    findings: list[SpecFinding] = []

    if not SPECS_DIR.exists():
        return findings

    for spec_path in sorted(SPECS_DIR.glob("*.md")):
        if limit_spec and spec_path.stem != limit_spec:
            continue

        content = read_text(spec_path)
        meta, body = parse_frontmatter(content)
        title = str(meta.get("title") or first_heading(body))
        status = str(meta.get("status") or "unknown")
        owner = str(meta.get("owner") or "unassigned")
        targets = normalize_list(meta.get("target_projects") or meta.get("linked_projects"))
        required_capabilities = normalize_list(meta.get("required_capabilities"))
        open_items = count_open_checkboxes(body)
        freshness_days = 0
        try:
            freshness_days = max(0, (datetime.now(timezone.utc) - datetime.fromtimestamp(spec_path.stat().st_mtime, tz=timezone.utc)).days)
        except Exception:
            freshness_days = 0

        notes: list[str] = []
        if not meta:
            notes.append("legacy spec (missing frontmatter)")
        if owner == "unassigned":
            notes.append("owner not declared")
        if not targets:
            notes.append("no target_projects declared")

        missing_targets = [t for t in targets if t not in projects]
        if missing_targets:
            notes.append(f"missing target project(s): {', '.join(missing_targets)}")

        for capability in required_capabilities:
            if capability not in providers:
                notes.append(f"no provider found for {capability}")

        if open_items:
            notes.append(f"{open_items} open checklist item(s)")
        if freshness_days >= 7 and open_items:
            notes.append("stale spec with unresolved checklist items")

        # Surface likely drift when a target project remains proposed.
        for target in targets:
            project = projects.get(target)
            if project is None:
                continue
            project_status = str(getattr(project, "status", "") or "")
            if "Proposed" in project_status and (open_items or required_capabilities):
                notes.append(f"target `{target}` still proposed")
                break

        findings.append(
            SpecFinding(
                spec=spec_path.stem,
                title=title,
                status=status,
                owner=owner,
                targets=targets,
                required_capabilities=required_capabilities,
                open_items=open_items,
                freshness_days=freshness_days,
                notes=notes,
            )
        )

    return findings


def render_report(findings: list[SpecFinding]) -> str:
    aligned = [f for f in findings if not f.notes]
    needs_attention = [f for f in findings if f.notes]
    lines = [
        "# 📐 Spec Steward Report",
        "",
        f"- **Scanned**: {len(findings)} spec(s)",
        f"- **Aligned**: {len(aligned)}",
        f"- **Needs Attention**: {len(needs_attention)}",
        "",
        "| Spec | Status | Owner | Targets | Open Items | Fresh (days) | Notes |",
        "| :--- | :--- | :--- | :--- | :---: | :---: | :--- |",
    ]

    for item in findings:
        notes = "; ".join(item.notes) if item.notes else "aligned"
        targets = ", ".join(item.targets) if item.targets else "—"
        lines.append(
            f"| **{item.spec}** | {item.status} | {item.owner} | {targets} | {item.open_items} | {item.freshness_days} | {notes} |"
        )

    lines.extend([
        "",
        "## Steward Notes",
        "- Specs should declare ownership and target projects.",
        "- Open checklist items indicate the spec is not yet fully closed.",
        "- A spec is considered healthy only when the implementation path is visible in project declarations or status updates.",
    ])
    return "\n".join(lines)


def write_report(report: str) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    report_path = REPORT_DIR / f"report_{timestamp}.md"
    report_path.write_text(report, encoding="utf-8")
    return report_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate an AgentOS spec governance report.")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of markdown.")
    parser.add_argument("--spec", help="Limit to a single spec slug (filename without .md).")
    args = parser.parse_args()

    findings = build_findings(args.spec)
    if args.json:
        print(json.dumps([asdict(item) for item in findings], ensure_ascii=False, indent=2))
        return 0

    report = render_report(findings)
    report_path = write_report(report)
    print(report)
    print("")
    print(f"Saved to: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
