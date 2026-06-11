#!/usr/bin/env python3
import os
import sys
import subprocess
import argparse
import yaml
from pathlib import Path

# Setup path for agent_core imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(PROJECT_ROOT))
from agent_core import project_store, config

def add_project_to_workspace(project_id, workspace_name):
    project_dir = config.PROJECTS_DIR / project_id
    yaml_path = project_dir / "project.yaml"
    
    if not yaml_path.exists():
        print(f"❌ Error: Project settings not found for '{project_id}' at {yaml_path}")
        sys.exit(1)
        
    try:
        with open(yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except Exception as e:
        print(f"❌ Error loading project YAML: {e}")
        sys.exit(1)
        
    target_workspaces = data.get("target_workspaces") or []
    if isinstance(target_workspaces, str):
        target_workspaces = [target_workspaces]
    else:
        target_workspaces = list(target_workspaces)
        
    if workspace_name not in target_workspaces:
        target_workspaces.append(workspace_name)
        data["target_workspaces"] = target_workspaces
        
        try:
            with open(yaml_path, "w", encoding="utf-8") as f:
                yaml.dump(data, f, allow_unicode=True, default_flow_style=False)
            print(f"✅ Added workspace '{workspace_name}' to project '{project_id}' target list.")
        except Exception as e:
            print(f"❌ Error saving project YAML: {e}")
            sys.exit(1)
    else:
        print(f"ℹ️  Project '{project_id}' is already targeted for workspace '{workspace_name}'.")

def remove_project_from_workspace(project_id, workspace_name):
    project_dir = config.PROJECTS_DIR / project_id
    yaml_path = project_dir / "project.yaml"
    
    if not yaml_path.exists():
        print(f"❌ Error: Project settings not found for '{project_id}' at {yaml_path}")
        sys.exit(1)
        
    try:
        with open(yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except Exception as e:
        print(f"❌ Error loading project YAML: {e}")
        sys.exit(1)
        
    target_workspaces = data.get("target_workspaces") or []
    if isinstance(target_workspaces, str):
        target_workspaces = [target_workspaces]
    else:
        target_workspaces = list(target_workspaces)
        
    if workspace_name in target_workspaces:
        target_workspaces.remove(workspace_name)
        data["target_workspaces"] = target_workspaces
        
        try:
            with open(yaml_path, "w", encoding="utf-8") as f:
                yaml.dump(data, f, allow_unicode=True, default_flow_style=False)
            print(f"✅ Removed workspace '{workspace_name}' from project '{project_id}' target list.")
        except Exception as e:
            print(f"❌ Error saving project YAML: {e}")
            sys.exit(1)
    else:
        print(f"ℹ️  Project '{project_id}' is not targeted for workspace '{workspace_name}'.")

def reconcile():
    current_ws = config.WORKSPACE_NAME
    home_dir = Path.home()
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
        
        local_path = home_dir / p.project_id
        
        if is_target:
            to_ensure.append(p)
        else:
            # If it exists here but is NOT in target_workspaces, we might want to flag it
            if local_path.exists():
                to_remove.append(p)

    # 2. Execute Action: Ensure
    print(f"\n📥 Ensuring {len(to_ensure)} targeted projects...")
    for p in to_ensure:
        target_path = home_dir / p.project_id
        if not target_path.exists():
            if not p.repo_url:
                print(f"⚠️  {p.project_id}: Cannot clone, no repo_url found in project.yaml")
                continue
            
            print(f"📥 {p.project_id}: Cloning from {p.repo_url}...")
            subprocess.run(["git", "clone", p.repo_url, str(target_path)])
        
        # Registration (Symlinks)
        print(f"🔗 {p.project_id}: Syncing registration via import_project script...")
        subprocess.run([
            "python3", str(PROJECT_ROOT / "scripts" / "import_project.py"),
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
    parser = argparse.ArgumentParser(description="Reconcile AgentOS projects with the local workspace.")
    parser.add_argument("--add", help="Add a project to this computer's workspace by its slug")
    parser.add_argument("--remove", help="Remove a project from this computer's workspace by its slug")
    args = parser.parse_args()
    
    current_ws = config.WORKSPACE_NAME
    
    if args.add:
        add_project_to_workspace(args.add, current_ws)
    elif args.remove:
        remove_project_from_workspace(args.remove, current_ws)
        
    reconcile()
    
    # Regenerate VS Code workspace file
    workspace_script = PROJECT_ROOT / "scripts" / "gen_workspace.py"
    if workspace_script.exists():
        print(f"\n🔄 Regenerating VS Code workspace file...")
        subprocess.run(["python3", str(workspace_script)])
