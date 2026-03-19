#!/usr/bin/env python3
import os
import re

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
DATA_ROOT = os.getenv("AGENT_DATA_ROOT")

FRONTMATTER_TEMPLATE = """---
priority: 5
category: research
lifecycle_stage: execution
due_date: 
tags: []
---

"""

def migrate_status_file(filepath):
    with open(filepath, "r") as f:
        content = f.read()

    # Check if frontmatter already exists
    if content.startswith("---"):
        print(f"⏭️  Skipping {filepath} (Already migrated)")
        return False

    print(f"💉 Injecting metadata into {filepath}")
    new_content = FRONTMATTER_TEMPLATE + content
    with open(filepath, "w") as f:
        f.write(new_content)
    return True

def run_migration():
    print("🚀 Starting Data Migration to v1.1.0...")
    
    if not DATA_ROOT:
        print("❌ Error: AGENT_DATA_ROOT not set.")
        return

    projects_dir = os.path.join(DATA_ROOT, "projects")
    if not os.path.exists(projects_dir):
        print("❌ Projects directory not found.")
        return

    count = 0
    for root, dirs, files in os.walk(projects_dir):
        for file in files:
            if file == "STATUS.md":
                path = os.path.join(root, file)
                if migrate_status_file(path):
                    count += 1

    # Update Version File
    version_file = os.path.join(DATA_ROOT, ".version")
    with open(version_file, "w") as f:
        f.write("1.1.0\n")

    print(f"\n✅ Migration Complete. {count} files updated. Data layer version set to 1.1.0")

if __name__ == "__main__":
    run_migration()
