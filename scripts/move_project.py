#!/usr/bin/env python3
import os
import sys
import shutil

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

SECTORS = ["ideas", "specs", "projects", "validation"]

def move_project(slug, target_sector):
    if target_sector not in SECTORS:
        print(f"❌ Error: Invalid target sector '{target_sector}'. Choose from {SECTORS}")
        return

    # 1. Locate current sector
    current_sector = None
    source_path = None
    for s in SECTORS:
        p = os.path.join(DATA_ROOT, s, slug)
        if os.path.exists(p):
            current_sector = s
            source_path = p
            break
    
    # Check if slug is a file instead of a directory (common for ideas)
    if not source_path:
        for s in SECTORS:
            p = os.path.join(DATA_ROOT, s, f"{slug}.md")
            if os.path.exists(p):
                current_sector = s
                source_path = p
                break

    if not current_sector:
        print(f"❌ Error: Project '{slug}' not found in any sector.")
        return

    if current_sector == target_sector:
        print(f"⏭️  Project '{slug}' is already in '{target_sector}'.")
        return

    # 2. Prepare target
    target_path = os.path.join(DATA_ROOT, target_sector, os.path.basename(source_path))
    
    # Handle filename adjustment (if moving from a single .md to a folder project)
    if source_path.endswith(".md") and target_sector in ["projects"]:
        # Promote file to a folder
        new_folder = os.path.join(DATA_ROOT, target_sector, slug)
        os.makedirs(new_folder, exist_ok=True)
        target_path = os.path.join(new_folder, "STATUS.md")
        print(f"📁 Promoting file to project folder: {slug}")
        shutil.move(source_path, target_path)
    else:
        print(f"🚚 Moving {source_path} to {target_path}")
        shutil.move(source_path, target_path)

    # 3. Update Lifecycle Metadata
    status_file = target_path if target_path.endswith(".md") else os.path.join(target_path, "STATUS.md")
    if os.path.exists(status_file):
        with open(status_file, "r") as f:
            content = f.read()
        
        # Simple regex update for lifecycle_stage
        new_content = re.sub(r"lifecycle_stage:.*", f"lifecycle_stage: {target_sector}", content)
        with open(status_file, "w") as f:
            f.write(new_content)
        print(f"📝 Updated lifecycle_stage to: {target_sector}")

    print(f"✅ Success: '{slug}' moved from {current_sector} to {target_sector}.")

if __name__ == "__main__":
    import re
    if len(sys.argv) < 3:
        print("Usage: ./move_project.py <slug> <target_sector>")
        sys.exit(1)
    
    move_project(sys.argv[1], sys.argv[2])
