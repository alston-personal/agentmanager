#!/usr/bin/env python3
import os
from pathlib import Path

# Paths
DATA_ROOT = Path("/home/ubuntu/agent-data")
SNAPSHOTS_DIR = DATA_ROOT / "memory/snapshots"
CHRONICLE_FILE = DATA_ROOT / "CHRONICLE.md"

KEYWORDS = ["v0.5.1", "繼承", "Inheritance", "LCS-Signal", "PM2", "Vaultwarden", "n8n"]

def recall():
    print("🌅 [Recall Protocol] Searching for lost truths in snapshots...")
    history = []
    
    if not SNAPSHOTS_DIR.exists():
        print("❌ No snapshots found.")
        return

    # Scan snapshots from newest to oldest
    snapshot_files = sorted(SNAPSHOTS_DIR.glob("*.md"), reverse=True)
    
    for sf in snapshot_files:
        content = sf.read_text()
        blocks = []
        # Primitive but reliable extraction: Find lines containing the keywords
        lines = content.split("\n")
        relevant_blocks = []
        for i, line in enumerate(lines):
            if any(kw.lower() in line.lower() for kw in KEYWORDS):
                # Grab a few lines of context around the hit
                start = max(0, i - 5)
                end = min(len(lines), i + 10)
                relevant_blocks.append("\n".join(lines[start:end]))
        
        if relevant_blocks:
            history.append(f"### Snapshot: {sf.name}\n" + "\n---\n".join(relevant_blocks))

    # Synthesize the Chronicle
    with open(CHRONICLE_FILE, "w") as f:
        f.write("# 🏛️ AgentOS 歷史編年史 (The Chronicle)\n")
        f.write("> 此檔案由 scripts/recall_chronicle.py 自動生成。本質為固化之長期記憶。\n\n")
        f.write("\n\n".join(history))
        
    print(f"✅ Chronicle updated: {CHRONICLE_FILE}")

if __name__ == '__main__':
    recall()
