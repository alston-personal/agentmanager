#!/usr/bin/env python3
import os
import sys
import shutil
from datetime import datetime

PROJECT_ROOT = os.getenv("AGENT_PROJECT_ROOT", os.getcwd())
SYNC_FILE = os.path.join(PROJECT_ROOT, "memory/session_sync.md")
ARCHIVE_DIR = os.path.join(PROJECT_ROOT, "memory/archive")

def main():
    if not os.path.exists(SYNC_FILE):
        print("❌ No session_sync.md found.")
        return

    size_kb = os.path.getsize(SYNC_FILE) / 1024
    print(f"📊 Current Sync Buffer Size: {size_kb:.2f} KB")

    # 手動或自動觸發
    if size_kb < 30 and "--force" not in sys.argv:
        print("✅ Buffer size is healthy. No compression needed.")
        return

    print("🚀 Triggering AI Memory Compression...")
    
    # 1. Archive
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    archive_path = os.path.join(ARCHIVE_DIR, f"session_sync_{timestamp}.md")
    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    shutil.copy2(SYNC_FILE, archive_path)
    print(f"📦 Original archived to {archive_path}")

    # 2. Preparation for AI
    print("\n--- [ACTION REQUIRED BY AGENT] ---")
    print("Please read the following rules and perform a 'Memory Snapshot' conversion:")
    print(f"Rules: .agent/rules/COMPRESSION_PROMPT.md")
    print(f"Input: {SYNC_FILE}")
    print("\nAfter generating the snapshot, overwrite 'session_sync.md' with the result.")
    print("----------------------------------\n")

if __name__ == "__main__":
    main()
