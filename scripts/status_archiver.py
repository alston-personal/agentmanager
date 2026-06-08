#!/usr/bin/env python3
"""
status_archiver.py - Rolls over old logs from STATUS.md into archive/status_history.md.
Retains only the top N entries in the active STATUS.md.
"""

import os
import re
from pathlib import Path
from datetime import datetime

AGENT_DATA_ROOT = Path(os.getenv("AGENT_DATA_ROOT", "/home/dqa03/agent-data"))
PROJECTS_DIR = AGENT_DATA_ROOT / "projects"
KEEP_LATEST = 20

def archive_status_file(status_path: Path):
    if not status_path.exists():
        return

    content = status_path.read_text(encoding="utf-8")
    
    start_marker = "<!-- LOG_START -->"
    end_marker = "<!-- LOG_END -->"
    
    if start_marker not in content or end_marker not in content:
        return
        
    pre_log, rest = content.split(start_marker, 1)
    log_content, post_log = rest.split(end_marker, 1)
    
    # Extract logs (assuming they start with '- ' or similar, splitting by lines)
    # We will try to preserve blank lines but count actual entries.
    lines = log_content.strip("\n").split("\n")
    entries = []
    current_entry = []
    
    for line in lines:
        if line.strip().startswith("- `") or line.strip().startswith("- **"):
            if current_entry:
                entries.append("\n".join(current_entry))
            current_entry = [line]
        elif line.strip() == "":
            if current_entry:
                current_entry.append(line)
        else:
            if current_entry:
                current_entry.append(line)
            else:
                current_entry = [line]
    
    if current_entry:
        entries.append("\n".join(current_entry))
        
    if len(entries) <= KEEP_LATEST:
        return # Nothing to archive
        
    to_keep = entries[:KEEP_LATEST]
    to_archive = entries[KEEP_LATEST:]
    
    # Write to archive
    archive_dir = status_path.parent / "archive"
    archive_dir.mkdir(exist_ok=True)
    archive_file = archive_dir / "status_history.md"
    
    with open(archive_file, "a", encoding="utf-8") as f:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        f.write(f"\n\n### Archived on {timestamp}\n")
        f.write("\n".join(to_archive))
        f.write("\n")
        
    # Overwrite STATUS.md
    new_log_content = "\n" + "\n".join(to_keep) + "\n"
    new_content = pre_log + start_marker + new_log_content + end_marker + post_log
    
    status_path.write_text(new_content, encoding="utf-8")
    print(f"✅ Archived {len(to_archive)} logs from {status_path.parent.name}")

def main():
    if not PROJECTS_DIR.exists():
        print(f"❌ Projects directory not found at {PROJECTS_DIR}")
        return
        
    for proj_dir in PROJECTS_DIR.iterdir():
        if proj_dir.is_dir():
            status_file = proj_dir / "STATUS.md"
            archive_status_file(status_file)
            
if __name__ == "__main__":
    main()
