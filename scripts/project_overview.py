#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

import yaml


def read_file(path):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return ""


def read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def short_sha(value):
    return str(value)[:12] if value else "-"


def main():
    if len(sys.argv) < 2:
        project_dir = os.getcwd()
    else:
        project_dir = sys.argv[1]

    project_yaml_path = Path(project_dir) / "project.yaml"
    status_path = os.path.join(project_dir, "STATUS.md")
    short_term_path = os.path.join(project_dir, "memory", "SHORT_TERM.md")
    execution_head_path = os.path.join(project_dir, "execution-head.json")

    if not os.path.exists(status_path):
        print(f"❌ Error: Not a project directory (STATUS.md missing at {project_dir})")
        return

    status_content = read_file(status_path)
    short_term_content = read_file(short_term_path)
    execution = read_json(execution_head_path)
    project_yaml = {}
    if project_yaml_path.exists():
        try:
            project_yaml = yaml.safe_load(project_yaml_path.read_text(encoding="utf-8")) or {}
        except Exception:
            project_yaml = {}

    print("\n" + "="*40)
    print("🎯 PROJECT MISSION BRIEF")
    print("="*40)

    summary = "No summary found."
    if "## 📍 Summary" in status_content:
        summary_section = status_content.split("## 📍 Summary")[1].split("##")[0].strip()
        summary = summary_section

    provided = project_yaml.get("capabilities_provided") or []
    required = project_yaml.get("capabilities_required") or []
    if isinstance(provided, str):
        provided = [provided]
    if isinstance(required, str):
        required = [required]

    todos = []
    if "## 📅 Todo List" in status_content:
        todo_section = status_content.split("## 📅 Todo List")[1].split("##")[0].strip()
        todos = [line.strip() for line in todo_section.split("\n") if "[ ]" in line]

    active_tasks = []
    if "## 🚧 Pending Tasks" in short_term_content:
        active_section = short_term_content.split("## 🚧 Pending Tasks")[1].split("##")[0].strip()
        active_tasks = [line.strip() for line in active_section.split("\n") if "[ ]" in line or line.startswith("-")]

    print(f"\n📍 STATUS SUMMARY:\n{summary}")

    if execution:
        print("\n⚙️ EXECUTION HEAD (runtime evidence):")
        print(f"  Node:        {execution.get('node') or '-'}")
        print(f"  Workspace:   {execution.get('workspace') or '-'}")
        print(f"  Branch:      {execution.get('branch') or '-'}")
        print(f"  Version:     {execution.get('version') or '-'}")
        print(f"  Local HEAD:  {short_sha(execution.get('local_head'))}")
        print(f"  Upstream:    {execution.get('upstream') or '-'}")
        print(f"  Remote HEAD: {short_sha(execution.get('remote_head'))}")
        print(f"  Ahead/Behind:{execution.get('ahead')} / {execution.get('behind')}")
        print(f"  Dirty:       {execution.get('dirty')}")
        print(f"  Latest Tag:  {execution.get('latest_tag') or '-'}")
        print(f"  Observed:    {execution.get('observed_at') or '-'}")
        if execution.get("error"):
            print(f"  ⚠ Collector error: {execution.get('error')}")
        if isinstance(execution.get("ahead"), int) and execution["ahead"] > 0:
            print(f"  ⚠ LOCAL EXECUTION IS {execution['ahead']} COMMIT(S) AHEAD OF REMOTE.")
            print("    Do not treat the remote branch or STATUS.md as the current implementation head.")

    if provided or required:
        print("\n🧩 CAPABILITY DECLARATIONS:")
        if provided:
            print("  Provided:")
            for item in provided:
                print(f"    - {item}")
        if required:
            print("  Required:")
            for item in required:
                print(f"    - {item}")

    print("\n📅 CORE ROADMAP (from STATUS.md):")
    for t in todos[:5]:
        print(f"  {t}")

    print("\n🚧 ACTIVE SESSION TASKS (from SHORT_TERM.md):")
    for t in active_tasks[:5]:
        print(f"  {t}")

    print("\n💡 ADVICE FOR THE AGENT:")
    if execution and execution.get("local_head"):
        print("  1. Treat the fresh execution receipt as implementation evidence; surface any drift from remote/STATUS.")
        print("  2. Continue from the active local workspace unless a fresher trusted receipt supersedes it.")
        print("  3. Update STATUS.md after major success; do not use it to overwrite a newer execution head.")
    else:
        print("  1. No valid execution receipt is available; inspect the registered workspace before assuming GitHub is current.")
        print("  2. Focus on the first [ ] task in the 'Active Session' list.")
        print("  3. Update the 'Activity Log' in STATUS.md after every major success.")
    print("  4. Run '/report' before leaving to ensure context is passed to the next agent.")
    print("="*40 + "\n")


if __name__ == "__main__":
    main()
