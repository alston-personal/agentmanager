#!/usr/bin/env python3
import os
import sys
import argparse
import subprocess
from pathlib import Path

# Add project root to sys.path to import agent_core
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(PROJECT_ROOT))
from agent_core import project_store

def sync_sector(sector_name):
    print(f"🔄 Syncing projects for Sector: {sector_name}...")
    projects = project_store.list_projects(sector=sector_name)
    
    if not projects:
        print(f"⚠️ No projects found in sector '{sector_name}'.")
        return

    for p in projects:
        if not p.repo_url:
            print(f"⏩ Skipping {p.project_id} (No repo_url defined)")
            continue
            
        # Determine target path relative to user home
        target_path = Path.home() / p.project_id
        if target_path.exists():
            print(f"📦 {p.project_id} already exists, skipping clone.")
        else:
            print(f"📥 Cloning {p.project_id} from {p.repo_url}...")
            subprocess.run(["git", "clone", p.repo_url, str(target_path)])
        
        # Ensure it's registered locally (symlinks)
        print(f"🔗 Linking {p.project_id} to Agent OS...")
        subprocess.run([
            "python3", str(PROJECT_ROOT / "scripts" / "import_project.py"),
            str(target_path), "--sector", p.sector
        ])

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sync projects by Sector/Category")
    parser.add_argument("--sector", required=True, help="Sector name to sync (e.g. Work)")
    args = parser.parse_args()
    sync_sector(args.sector)
