#!/usr/bin/env python3
import os
import subprocess
import argparse
from pathlib import Path
from datetime import datetime, timezone
import yaml

# Path resolution
AGENTMANAGER_ROOT = Path("/home/ubuntu/agentmanager")
AGENT_DATA_ROOT = Path("/home/ubuntu/agent-data")

def get_git_remote(path):
    try:
        result = subprocess.run(
            ["git", "-C", str(path), "remote", "get-url", "origin"],
            capture_output=True, text=True, check=True
        )
        return result.stdout.strip()
    except:
        return None

def import_project(source_path, sector="Work"):
    source_path = Path(source_path).resolve()
    project_id = source_path.name
    
    print(f"🔍 Importing existing project: {project_id} from {source_path}")
    
    repo_url = get_git_remote(source_path)
    data_dir = AGENT_DATA_ROOT / "projects" / project_id
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "memory").mkdir(exist_ok=True)
    
    now = datetime.now(timezone.utc).isoformat()
    # If the user is importing locally, assume this workspace is a target
    workspace_name = os.environ.get("WORKSPACE_NAME", "oracle-vm")

    project_metadata = {
        "project_id": project_id,
        "display_name": project_id.replace("-", " ").title(),
        "phase": "active",
        "status": "⭐ Imported",
        "sector": sector,
        "repo_url": repo_url,
        "actual_code_path": str(source_path),
        "data_path": str(data_dir),
        "target_workspaces": [workspace_name],
        "created_at": now,
        "updated_at": now,
        "health": {"freshness": "fresh", "sync_state": "synced"}
    }
    
    with open(data_dir / "project.yaml", "w") as f:
        yaml.dump(project_metadata, f, allow_unicode=True)

    # Register via existing script (handles STATUS.md and Dashboard)
    subprocess.run([
        "python3", str(AGENTMANAGER_ROOT / "scripts" / "register_project.py"),
        project_id, "--display-name", project_metadata["display_name"]
    ])

    print(f"✅ Successfully imported {project_id} under Sector: {sector}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import an existing folder as an Agent OS project")
    parser.add_argument("path", help="Path to the project folder")
    parser.add_argument("--sector", default="Work", help="Sector/Category (Work/Creative/Product)")
    args = parser.parse_args()
    import_project(args.path, args.sector)
