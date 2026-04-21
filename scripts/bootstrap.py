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

DATA_ROOT = os.getenv("AGENT_DATA_ROOT") or os.getenv("AGENT_DATA_DIR")
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
    if os.path.islink(link_path):
        existing_target = os.readlink(link_path)
        if existing_target != target_path:
            print(f"🔗 Updating symlink: {label} -> {target_path}")
            os.remove(link_path)
            os.symlink(target_path, link_path)
    elif os.path.exists(link_path):
        print(f"⚠️ Warning: {label} exists as a real path in logic repo. Skipping symlink.")
    else:
        print(f"🔗 Creating symlink: {label} -> {target_path}")
        os.symlink(target_path, link_path)

def bootstrap():
    print("🚀 Starting Agent OS Data Layer Bootstrap...")
    
    if not DATA_ROOT:
        print("❌ Error: AGENT_DATA_ROOT not set in environment.")
        sys.exit(1)

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
            with open(target, "w") as f:
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
