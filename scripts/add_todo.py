#!/usr/bin/env python3
import os
import sys
import re

# ⚙️ Configuration
PROJECT_ROOT = os.getenv("AGENT_PROJECT_ROOT", os.getcwd())
ENV_FILE = os.path.join(PROJECT_ROOT, ".env")

def load_env():
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, "r") as f:
            for line in f:
                if "=" in line and not line.startswith("#"):
                    key, val = line.strip().split("=", 1)
                    os.environ[key] = val.strip('"').strip("'")

load_env()
DATA_ROOT = os.getenv("AGENT_DATA_ROOT", "/home/ubuntu/agent-data")

def add_todo(slug, task_text):
    # 1. Locate the project status file across all sectors
    sectors = ["projects", "specs", "ideas", "validation"]
    status_path = None
    for s in sectors:
        p = os.path.join(DATA_ROOT, s, slug, "STATUS.md")
        if os.path.exists(p):
            status_path = p
            break
        # Also check for single file projects (like ideas)
        p = os.path.join(DATA_ROOT, s, f"{slug}.md")
        if os.path.exists(p):
            status_path = p
            break

    if not status_path:
        print(f"❌ Error: Project '{slug}' not found.")
        return False

    # 2. Read and modify content
    with open(status_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Find the Todo List section (case-insensitive, optional emoji)
    todo_header_pattern = r"(## (?:📅 )?Todo List\n)"
    match = re.search(todo_header_pattern, content, re.I)
    
    if not match:
        # If section missing, append it at the end
        new_content = content + f"\n\n## 📅 Todo List\n- [ ] {task_text}\n"
    else:
        # Insert after the header
        header_end = match.end()
        new_content = content[:header_end] + f"- [ ] {task_text}\n" + content[header_end:]

    with open(status_path, "w", encoding="utf-8") as f:
        f.write(new_content)

    print(f"✅ Success: Task added to {slug}.")
    return True

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: ./add_todo.py <project_slug> <task_text>")
        sys.exit(1)
    
    add_todo(sys.argv[1], sys.argv[2])
