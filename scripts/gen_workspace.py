import json
import os
from pathlib import Path

def generate_workspace():
    template_path = Path("agentos.code-workspace.template")
    output_path = Path("agentos.code-workspace")
    
    if not template_path.exists():
        print("❌ Error: agentos.code-workspace.template not found!")
        return

    with open(template_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    original_folders = config.get("folders", [])
    active_folders = []

    print("🔍 Scanning for local project entities...")
    
    for folder in original_folders:
        path_str = folder.get("path")
        # Handle special case for current dir
        if path_str == ".":
            active_folders.append(folder)
            continue
            
        # Check if sibling directory exists
        physical_path = Path(path_str)
        if physical_path.exists():
            print(f"✅ Found: {folder.get('name')} ({path_str})")
            active_folders.append(folder)
        else:
            # Check if it's relative to the parent context
            # (In case script is run from agentmanager root)
            if (Path("..") / path_str).exists() or path_str.startswith(".."):
                # Workspace paths are relative to the workspace file
                # If path starts with ../ we need to resolve it relative to current dir
                # which is agentmanager root.
                if Path(path_str).exists():
                     active_folders.append(folder)
                     print(f"✅ Found: {folder.get('name')} ({path_str})")
                else:
                     print(f"➖ Skipping (Missing): {folder.get('name')}")
            else:
                print(f"➖ Skipping (Missing): {folder.get('name')}")

    config["folders"] = active_folders
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    
    print(f"\n🚀 Success! Created local '{output_path}' with {len(active_folders)} projects.")
    print("👉 Now simply open this file with your IDE to start working.")

if __name__ == "__main__":
    generate_workspace()
