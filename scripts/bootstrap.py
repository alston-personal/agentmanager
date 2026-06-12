#!/usr/bin/env python3
import os
import sys
import shutil

# ⚙️ Configuration
import sys
from pathlib import Path

PROJECT_ROOT_DETECTED = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT_DETECTED) not in sys.path:
    sys.path.append(str(PROJECT_ROOT_DETECTED))

from agent_core.memory_router import resolve_project_root, resolve_memory_route

PROJECT_ROOT = str(resolve_project_root())
ENV_FILE = os.path.join(PROJECT_ROOT, ".env")

def load_env():
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            for line in f:
                if "=" in line and not line.startswith("#"):
                    key, val = line.strip().split("=", 1)
                    os.environ[key] = val.strip('"').strip("'")

load_env()

route = resolve_memory_route()
DATA_ROOT = str(route.data_root)
SEED_DIR = os.path.join(PROJECT_ROOT, "templates/data-layer-seed")

MANDATORY_FOLDERS = ["ideas", "specs", "projects", "validation", "memory", "journals", "logs"]
MANDATORY_FILES = [".version", "README.md", "STATUS_TEMPLATE.md"]
MANDATORY_DATA_FILES = {
    "ARCHITECTURE.md": "# AgentOS Architecture\n\nInitialized by AgentOS bootstrap.\n",
}
LINK_BRIDGES = {
    "ideas": "ideas",
    "specs": "specs",
    "projects": "projects",
    "projects_status": "projects",
    "validation": "validation",
    "memory": "memory",
    "journals": "journals",
    "logs": "logs",
    "knowledge": "knowledge",
}
FILE_BRIDGES = {
    "ARCHITECTURE.md": "ARCHITECTURE.md",
}

def ensure_symlink(link_path, target_path, label):
    import subprocess
    link_path = os.path.normpath(link_path)
    target_path = os.path.normpath(target_path)
    
    if os.path.islink(link_path):
        try:
            existing_target = os.readlink(link_path)
        except Exception:
            existing_target = ""
        if os.path.normpath(existing_target) != target_path:
            print(f"🔗 Updating link: {label} -> {target_path}")
            try:
                if os.name == 'nt' and os.path.isdir(link_path):
                    os.rmdir(link_path)
                else:
                    os.unlink(link_path)
            except Exception:
                os.remove(link_path)
            create_link(target_path, link_path)
    elif os.path.exists(link_path):
        print(f"⚠️ Warning: {label} exists as a real path in logic repo. Skipping symlink.")
    else:
        print(f"🔗 Creating link: {label} -> {target_path}")
        create_link(target_path, link_path)

def create_link(target, link):
    import subprocess
    if os.name == 'nt':
        if os.path.isdir(target):
            subprocess.run(['cmd', '/c', 'mklink', '/j', link, target], check=True, shell=True)
        else:
            try:
                os.link(target, link)
            except OSError:
                shutil.copy2(target, link)
    else:
        os.symlink(target, link)

def heal_recursive_symlinks(root_dir):
    """
    Scans root_dir recursively for symbolic links that point to themselves or
    an ancestor path, creating infinite loops (cycles) that crash file explorers
    and search scripts. Automatically unlinks any detected cycle.
    """
    cleaned_count = 0
    for dirpath, dirnames, filenames in os.walk(root_dir):
        for entry in dirnames + filenames:
            entry_path = os.path.join(dirpath, entry)
            if os.path.islink(entry_path):
                try:
                    target = os.readlink(entry_path)
                    abs_target = os.path.abspath(os.path.join(os.path.dirname(entry_path), target))
                    abs_entry = os.path.abspath(entry_path)
                    
                    if abs_entry == abs_target or abs_entry.startswith(abs_target + os.sep):
                        print(f"🚨 Cycle Detected: {abs_entry} -> {target} (resolved: {abs_target})")
                        os.remove(abs_entry)
                        print(f"🗑️ Cleaned up recursive symlink cycle.")
                        cleaned_count += 1
                except Exception:
                    pass
    return cleaned_count

def bootstrap():
    print("🚀 Starting Agent OS Data Layer Bootstrap...")
    
    if not DATA_ROOT:
        print("❌ Error: AGENT_DATA_ROOT not set in environment.")
        sys.exit(1)
        
    # Auto-heal any symlink cycles to prevent freeze/lockup
    print("🔍 Auditing for recursive symlink cycles to prevent infinite loops...")
    cleaned = heal_recursive_symlinks(PROJECT_ROOT)
    if os.path.exists(DATA_ROOT):
        cleaned += heal_recursive_symlinks(DATA_ROOT)
    if cleaned > 0:
        print(f"✅ Self-healed {cleaned} symbolic link cycles.")
    else:
        print("☀️ No symbolic link cycles detected. System is clean.")


    print(f"📂 Target Data Root: {DATA_ROOT}")
    
    # 1. Ensure Folders
    for folder in sorted(set(MANDATORY_FOLDERS + list(LINK_BRIDGES.values()))):
        target = os.path.join(DATA_ROOT, folder)
        if not os.path.exists(target):
            print(f"✨ Creating missing folder: {folder}")
            os.makedirs(target, exist_ok=True)
            # Add .gitkeep if it's empty
            with open(os.path.join(target, ".gitkeep"), "w") as f:
                pass

    # 2. Ensure Mandatory Files
    for filename in MANDATORY_FILES:
        target = os.path.join(DATA_ROOT, filename)
        if not os.path.exists(target):
            print(f"📄 Seeding missing file: {filename}")
            shutil.copy2(os.path.join(SEED_DIR, filename), target)

    for filename, default_content in MANDATORY_DATA_FILES.items():
        target = os.path.join(DATA_ROOT, filename)
        if not os.path.exists(target):
            print(f"📄 Initializing data file: {filename}")
            with open(target, "w", encoding="utf-8") as f:
                f.write(default_content)

    # 3. Memory Structure Check
    memory_files = ["session_sync.md"] # Minimal set
    for mf in memory_files:
        target = os.path.join(DATA_ROOT, "memory", mf)
        if not os.path.exists(target):
            print(f"🧠 Initializing core memory: {mf}")
            with open(target, "w", encoding="utf-8") as f:
                f.write(f"# {mf}\n*Initialized @ {os.popen('date').read().strip()}*\n")

    # 4. Symlink Bridge Audit
    for link_name, target_name in LINK_BRIDGES.items():
        link_path = os.path.join(PROJECT_ROOT, link_name)
        target_path = os.path.join(DATA_ROOT, target_name)
        ensure_symlink(link_path, target_path, link_name)

    for link_name, target_name in FILE_BRIDGES.items():
        link_path = os.path.join(PROJECT_ROOT, link_name)
        target_path = os.path.join(DATA_ROOT, target_name)
        ensure_symlink(link_path, target_path, link_name)

    print("\n✅ Bootstrap Complete. Data layer is healthy and linked.")

if __name__ == "__main__":
    bootstrap()
