#!/usr/bin/env python3
"""
update_projects_pulse.py - Aggregates project states from STATUS.md into a high-speed JSON cache.
Writes to volatile RAM disk and persistent fallback.
"""

import os
import json
import re
from pathlib import Path
from datetime import datetime, timezone

AGENT_DATA_ROOT = Path(os.getenv("AGENT_DATA_ROOT", "/home/dqa03/agent-data"))
PROJECTS_DIR = AGENT_DATA_ROOT / "projects"

SHM_ROOT = Path("/dev/shm/leopardcat-swarm")
SHM_PULSE = SHM_ROOT / "projects_pulse.json"
PERSISTENT_PULSE = AGENT_DATA_ROOT / "runtime" / "projects_pulse_snapshot.json"

def parse_status_md(status_path: Path) -> dict:
    data = {
        "priority": 99,
        "category": "unknown",
        "lifecycle_stage": "unknown",
        "tags": [],
        "last_status": "Unknown",
        "last_updated": "Unknown",
        "pending_todos": 0
    }
    
    if not status_path.exists():
        return data
        
    content = status_path.read_text(encoding="utf-8")
    
    # Parse frontmatter
    fm_match = re.search(r"^---\n(.*?)\n---", content, re.DOTALL)
    if fm_match:
        fm = fm_match.group(1)
        for line in fm.split("\n"):
            if line.startswith("priority:"):
                try: data["priority"] = int(line.split(":")[1].strip())
                except: pass
            elif line.startswith("category:"):
                data["category"] = line.split(":")[1].strip()
            elif line.startswith("lifecycle_stage:"):
                data["lifecycle_stage"] = line.split(":")[1].strip()
                
    # Parse metrics
    for line in content.split("\n"):
        if "| **Last Status**" in line:
            parts = line.split("|")
            if len(parts) >= 3:
                data["last_status"] = parts[2].strip()
        elif "| **Last Updated**" in line:
            parts = line.split("|")
            if len(parts) >= 3:
                data["last_updated"] = parts[2].strip()
                
    # Count pending TODOs
    todo_match = re.search(r"## 📅 Todo List\n(.*)", content, re.DOTALL)
    if todo_match:
        todos = todo_match.group(1).split("\n")
        data["pending_todos"] = len([t for t in todos if t.strip().startswith("- [ ]")])
        
    return data

def main():
    SHM_ROOT.mkdir(parents=True, exist_ok=True)
    PERSISTENT_PULSE.parent.mkdir(parents=True, exist_ok=True)
    
    pulse_data = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "projects": {}
    }
    
    if PROJECTS_DIR.exists():
        for proj_dir in PROJECTS_DIR.iterdir():
            if proj_dir.is_dir():
                status_file = proj_dir / "STATUS.md"
                if status_file.exists():
                    pulse_data["projects"][proj_dir.name] = parse_status_md(status_file)
                    
    json_data = json.dumps(pulse_data, indent=2)
    
    SHM_PULSE.write_text(json_data, encoding="utf-8")
    PERSISTENT_PULSE.write_text(json_data, encoding="utf-8")
    
    print(f"✅ Pulse updated: {len(pulse_data['projects'])} projects cached.")

if __name__ == "__main__":
    main()
