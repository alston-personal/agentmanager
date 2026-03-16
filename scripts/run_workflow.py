#!/usr/bin/env python3
import os
import re
import sys
from glob import glob


PROJECT_ROOT = "/home/ubuntu/agentmanager"
AGENT_DATA_ROOT = os.environ.get("AGENT_DATA_ROOT", "/home/ubuntu/agent-data")
CENTRAL_PROJECTS_DIR = os.path.join(AGENT_DATA_ROOT, "projects")
WORKFLOWS_DIR = os.path.join(PROJECT_ROOT, ".agent", "workflows")
SKILL_WORKFLOWS_DIR = os.path.join(PROJECT_ROOT, ".agent", "skills", "workflows")


def normalize_workflow_name(raw_name: str) -> str:
    name = (raw_name or "").strip()
    if name.startswith("/"):
        name = name[1:]
    if name.startswith("workflow-"):
        name = name[len("workflow-"):]
    return name


def discover_workflows() -> list[str]:
    names = set()
    for folder in (WORKFLOWS_DIR, SKILL_WORKFLOWS_DIR):
        if not os.path.isdir(folder):
            continue
        for entry in os.listdir(folder):
            if entry.endswith(".md"):
                names.add(entry[:-3])
    return sorted(names)


def read_file(path: str) -> str:
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def extract_summary_field(content: str, label: str) -> str:
    pattern = rf"\|\s*\*\*{re.escape(label)}\*\*\s*\|\s*([^|]+?)\s*\|"
    match = re.search(pattern, content)
    return match.group(1).strip() if match else ""


def extract_latest_log(content: str) -> str:
    for line in content.splitlines():
        if line.startswith("- "):
            return line[2:].strip()
    return ""


def run_status() -> str:
    status_paths = sorted(glob(os.path.join(CENTRAL_PROJECTS_DIR, "*", "STATUS.md")))
    if not status_paths:
        return f"No project status files found in {CENTRAL_PROJECTS_DIR}."

    rows = []
    for status_path in status_paths:
        project_name = os.path.basename(os.path.dirname(status_path))
        content = read_file(status_path)
        rows.append({
            "project": project_name,
            "status": extract_summary_field(content, "Last Status") or "N/A",
            "updated": extract_summary_field(content, "Last Updated") or "N/A",
            "activity": extract_latest_log(content) or "N/A",
        })

    lines = [
        "| Project | Last Status | Last Updated | Latest Activity |",
        "| --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            f"| {row['project']} | {row['status']} | {row['updated']} | {row['activity']} |"
        )
    return "\n".join(lines)


def run_generic(workflow_name: str) -> str:
    workflow_paths = [
        os.path.join(WORKFLOWS_DIR, f"{workflow_name}.md"),
        os.path.join(SKILL_WORKFLOWS_DIR, f"{workflow_name}.md"),
    ]
    for workflow_path in workflow_paths:
        if os.path.exists(workflow_path):
            content = read_file(workflow_path)
            step_lines = [line.strip() for line in content.splitlines() if re.match(r"^\d+\.", line.strip())]
            response = [f"Workflow `/{workflow_name}` is loaded."]
            if step_lines:
                response.append("")
                response.append("Defined steps:")
                response.extend(step_lines)
            response.append("")
            response.append("Automatic execution is currently implemented for `/status`.")
            return "\n".join(response)
    available = ", ".join(f"/{name}" for name in discover_workflows()) or "(none)"
    return f"Unknown workflow: /{workflow_name}\nAvailable workflows: {available}"


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: run_workflow.py <workflow-name|/command|list>")
        return 1

    workflow_name = normalize_workflow_name(sys.argv[1])
    if workflow_name == "list":
        for name in discover_workflows():
            print(f"/{name}")
        return 0

    if workflow_name == "status":
        print(run_status())
        return 0

    print(run_generic(workflow_name))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
