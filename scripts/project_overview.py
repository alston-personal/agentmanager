#!/usr/bin/env python3
import os
import sys
from pathlib import Path

import yaml

def read_file(path):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return ""

def main():
    if len(sys.argv) < 2:
        project_dir = os.getcwd()
    else:
        project_dir = sys.argv[1]

    project_yaml_path = Path(project_dir) / "project.yaml"
    status_path = os.path.join(project_dir, "STATUS.md")
    short_term_path = os.path.join(project_dir, "memory", "SHORT_TERM.md")

    if not os.path.exists(status_path):
        print(f"❌ Error: Not a project directory (STATUS.md missing at {project_dir})")
        return

    status_content = read_file(status_path)
    short_term_content = read_file(short_term_path)
    project_yaml = {}
    if project_yaml_path.exists():
        try:
            project_yaml = yaml.safe_load(project_yaml_path.read_text(encoding="utf-8")) or {}
        except Exception:
            project_yaml = {}

    print("\n" + "="*40)
    print("🎯 PROJECT MISSION BRIEF")
    print("="*40)

    # 提取 Summary
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

    # 提取 Todo List (Pending only)
    todos = []
    if "## 📅 Todo List" in status_content:
        todo_section = status_content.split("## 📅 Todo List")[1].split("##")[0].strip()
        todos = [line.strip() for line in todo_section.split("\n") if "[ ]" in line]

    # 提取 Pending Tasks from short-term
    active_tasks = []
    if "## 🚧 Pending Tasks" in short_term_content:
        active_section = short_term_content.split("## 🚧 Pending Tasks")[1].split("##")[0].strip()
        active_tasks = [line.strip() for line in active_section.split("\n") if "[ ]" in line or line.startswith("-")]

    print(f"\n📍 STATUS SUMMARY:\n{summary}")

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
    for t in todos[:5]: print(f"  {t}")
    
    print("\n🚧 ACTIVE SESSION TASKS (from SHORT_TERM.md):")
    for t in active_tasks[:5]: print(f"  {t}")

    print("\n💡 ADVICE FOR THE AGENT:")
    print("  1. Focus on the first [ ] task in the 'Active Session' list.")
    print("  2. Update the 'Activity Log' in STATUS.md after every major success.")
    print("  3. Run '/report' before leaving to ensure context is passed to the next agent.")
    print("="*40 + "\n")

if __name__ == "__main__":
    main()
