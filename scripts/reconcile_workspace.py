#!/usr/bin/env python3
import os
import sys
import subprocess
import argparse
from pathlib import Path

# Setup path for agent_core imports
sys.path.append(str(Path(__file__).parent.parent))
from agent_core import project_store, config

def reconcile():
    current_ws = config.WORKSPACE_NAME
    print(f"🚀 Reconciling Workspace: {current_ws}")
    print(f"----------------------------------------")
    
    # List all known projects from the data layer
    all_projects = project_store.list_projects()
    
    # 1. Target detection
    to_ensure = []
    to_remove = []
    
    for p in all_projects:
        is_target = current_ws in p.target_workspaces
        
        # Also check sector for backward compatibility if needed, 
        # but let's stick to explicit target_workspaces for this new tool.
        
        local_path = Path("/home/ubuntu") / p.project_id
        
        if is_target:
            to_ensure.append(p)
        else:
            # If it exists here but is NOT in target_workspaces, we might want to flag it
            if local_path.exists():
                to_remove.append(p)

    # 2. Execute Action: Ensure
    print(f"\n📥 Ensuring {len(to_ensure)} targeted projects...")
    for p in to_ensure:
        target_path = Path("/home/ubuntu") / p.project_id
        if not target_path.exists():
            if not p.repo_url:
                print(f"⚠️  {p.project_id}: Cannot clone, no repo_url found in project.yaml")
                continue
            
            print(f"📥 {p.project_id}: Cloning from {p.repo_url}...")
            subprocess.run(["git", "clone", p.repo_url, str(target_path)])
        
        # Registration (Symlinks)
        print(f"🔗 {p.project_id}: Syncing registration via import_project script...")
        subprocess.run([
            "python3", "/home/ubuntu/agentmanager/scripts/import_project.py",
            str(target_path), "--sector", p.sector
        ])

    # 3. Report: Redundant projects
    if to_remove:
        print(f"\n🧹 Non-targeted projects found on this machine:")
        for p in to_remove:
            print(f"   - {p.project_id} (Not targeted for {current_ws})")
        print(f"   (Use 'rm -rf' manually if you wish to clean them up)")

    print(f"\n✅ Reconciliation complete for {current_ws}!")

if __name__ == "__main__":
    reconcile()
