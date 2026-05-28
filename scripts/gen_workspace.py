import json
import os
import sys
from pathlib import Path

# Setup path for agent_core imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(PROJECT_ROOT))
from agent_core import project_store, config

def generate_workspace():
    workspace_name = config.WORKSPACE_NAME
    template_path = PROJECT_ROOT / "agentos.code-workspace.template"
    output_path = PROJECT_ROOT / f"agentos.{workspace_name}.code-workspace"
    
    if not template_path.exists():
        print(f"❌ Error: {template_path} not found!")
        return

    with open(template_path, "r", encoding="utf-8") as f:
        workspace_config = json.load(f)

    original_folders = workspace_config.get("folders", [])
    active_folders = []

    print(f"🔍 Scanning projects targeted for workspace '{workspace_name}'...")
    
    # Load all registered projects from data layer
    all_projects = {p.project_id: p for p in project_store.list_projects()}

    for folder in original_folders:
        path_str = folder.get("path")
        # Handle special case for current dir (AgentOS Core)
        if path_str == ".":
            active_folders.append(folder)
            print(f"✅ Core: {folder.get('name')} ({path_str})")
            continue
            
        # Determine project_id from directory name
        project_id = Path(path_str).name
        
        # Check target workspace configuration
        if project_id in all_projects:
            project = all_projects[project_id]
            if workspace_name not in project.target_workspaces:
                print(f"➖ Skipping (Not targeted for {workspace_name}): {folder.get('name')}")
                continue

        # Check if directory exists
        physical_path = PROJECT_ROOT / path_str
        if physical_path.exists():
            print(f"✅ Found: {folder.get('name')} ({path_str})")
            active_folders.append(folder)
        else:
            # Sibling directory check or relative fallback
            if Path(path_str).exists():
                print(f"✅ Found: {folder.get('name')} ({path_str})")
                active_folders.append(folder)
            else:
                print(f"➖ Skipping (Missing directory): {folder.get('name')}")

    workspace_config["folders"] = active_folders
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(workspace_config, f, indent=2, ensure_ascii=False)
    
    print(f"\n🚀 Success! Created computer-specific '{output_path.name}' with {len(active_folders)} projects.")
    print("👉 Now simply open this file with your IDE to start working.")

if __name__ == "__main__":
    generate_workspace()

