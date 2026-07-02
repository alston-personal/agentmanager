#!/usr/bin/env python3
"""
toggle_project_indexing.py
==========================
Toggles which projects are actively watched and indexed by the IDE,
while keeping them in the folders list to preserve Agent permissions.
"""
import os
import sys
import json
import argparse
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WORKSPACE_FILE = PROJECT_ROOT / "agentos.code-workspace"

def load_workspace():
    if not WORKSPACE_FILE.exists():
        # Fallback to templates or instance-specific workspaces
        print(f"❌ Workspace file not found at {WORKSPACE_FILE}")
        sys.exit(1)
    
    try:
        with open(WORKSPACE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"❌ Failed to parse workspace JSON: {e}")
        sys.exit(1)

def save_workspace(data):
    try:
        with open(WORKSPACE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"✅ Successfully updated {WORKSPACE_FILE.name}")
    except Exception as e:
        print(f"❌ Failed to save workspace JSON: {e}")
        sys.exit(1)

def get_project_list(workspace_data):
    projects = []
    for folder in workspace_data.get("folders", []):
        path_str = folder.get("path", "")
        if path_str == ".":
            continue
        project_id = Path(path_str).name
        projects.append(project_id)
    return sorted(projects)

def get_current_status(workspace_data):
    settings = workspace_data.setdefault("settings", {})
    watcher_exclude = settings.setdefault("files.watcherExclude", {})
    
    projects = get_project_list(workspace_data)
    status = {}
    for p in projects:
        # If it's excluded from watcher, it's considered "Inactive" (not indexed)
        pattern = f"**/{p}/**"
        is_excluded = watcher_exclude.get(pattern, False)
        status[p] = "Inactive (Excluded)" if is_excluded else "Active (Indexed)"
    return status

def set_project_state(workspace_data, project_id, activate):
    settings = workspace_data.setdefault("settings", {})
    watcher_exclude = settings.setdefault("files.watcherExclude", {})
    search_exclude = settings.setdefault("search.exclude", {})
    files_exclude = settings.setdefault("files.exclude", {})
    
    pattern = f"**/{project_id}/**"
    
    if activate:
        # To activate, we remove the exclusion or set to false
        watcher_exclude[pattern] = False
        search_exclude[pattern] = False
        files_exclude[pattern] = False
        print(f"🔓 Activated indexing for project: {project_id}")
    else:
        # To deactivate, we exclude it
        watcher_exclude[pattern] = True
        search_exclude[pattern] = True
        files_exclude[pattern] = True
        print(f"🔒 Deactivated indexing for project: {project_id}")

def main():
    parser = argparse.ArgumentParser(description="Toggle AgentOS project indexing in VS Code workspace.")
    parser.add_argument("--status", action="store_true", help="Show indexing status of all projects.")
    parser.add_argument("--activate", metavar="PROJECT", help="Activate indexing for a project.")
    parser.add_argument("--deactivate", metavar="PROJECT", help="Deactivate indexing for a project.")
    parser.add_argument("--deactivate-all", action="store_true", help="Deactivate indexing for all projects except agentmanager.")
    args = parser.parse_args()
    
    workspace_data = load_workspace()
    projects = get_project_list(workspace_data)
    
    if args.status or (not args.activate and not args.deactivate and not args.deactivate_all):
        status = get_current_status(workspace_data)
        print("\n📊 AgentOS Project Indexing Status:")
        print("=" * 45)
        for p, stat in status.items():
            icon = "🟢" if "Active" in stat else "⚫"
            print(f"{icon} {p:<25} : {stat}")
        print("\n💡 Tip: Use --activate <project> or --deactivate <project> to toggle.")
        return
        
    if args.activate:
        if args.activate not in projects:
            print(f"❌ Project '{args.activate}' not found in workspace folders list.")
            sys.exit(1)
        set_project_state(workspace_data, args.activate, activate=True)
        save_workspace(workspace_data)
        
    elif args.deactivate:
        if args.deactivate not in projects:
            print(f"❌ Project '{args.deactivate}' not found in workspace folders list.")
            sys.exit(1)
        set_project_state(workspace_data, args.deactivate, activate=False)
        save_workspace(workspace_data)
        
    elif args.deactivate_all:
        print("🔒 Deactivating indexing for all projects...")
        for p in projects:
            # Keep agentmanager active by default, exclude others
            if p == "agentmanager":
                set_project_state(workspace_data, p, activate=True)
            else:
                set_project_state(workspace_data, p, activate=False)
        save_workspace(workspace_data)

if __name__ == "__main__":
    main()
