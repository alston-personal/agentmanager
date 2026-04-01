#!/usr/bin/env python3
import os
from pathlib import Path

# Dynamic Path Discovery (v0.6.2)
SCRIPT_DIR = Path(__file__).resolve().parent
LOGIC_ROOT = SCRIPT_DIR.parent
DATA_ROOT = (LOGIC_ROOT.parent / "agent-data")

if not DATA_ROOT.exists():
    # Fallback to home if not sibling
    DATA_ROOT = Path.home() / "agent-data"

SNAPSHOTS_DIR = DATA_ROOT / "memory/snapshots"
CHRONICLE_FILE = DATA_ROOT / "CHRONICLE.md"

KEYWORDS = ["v0.5.1", "繼承", "Inheritance", "LCS-Signal", "PM2", "Vaultwarden", "n8n"]

def recall():
    print(f"🌅 [Recall Protocol] Searching for truths in: {DATA_ROOT}")
    if not DATA_ROOT.exists():
        print(f"❌ Data Layer NOT FOUND at: {DATA_ROOT}")
        return

    history = []
    if not SNAPSHOTS_DIR.exists():
        print(f"❌ No snapshots found in: {SNAPSHOTS_DIR}")
        return

    snapshot_files = sorted(SNAPSHOTS_DIR.glob("*.md"), reverse=True)
    for sf in snapshot_files:
        content = sf.read_text()
        relevant_blocks = []
        lines = content.split("\n")
        for i, line in enumerate(lines):
            if any(kw.lower() in line.lower() for kw in KEYWORDS):
                start = max(0, i - 5)
                end = min(len(lines), i + 10)
                relevant_blocks.append("\n".join(lines[start:end]))
        
        if relevant_blocks:
            history.append(f"### Snapshot: {sf.name}\n" + "\n---\n".join(relevant_blocks))

    with open(CHRONICLE_FILE, "w") as f:
        f.write("# ��️ AgentOS 歷史編年史 (The Chronicle v2.1)\n")
        f.write(f"> 此檔案由 recall_chronicle.py 動態生成。 檢索路徑: {DATA_ROOT}\n\n")
        f.write("\n\n".join(history))
        
    print(f"✅ Chronicle updated: {CHRONICLE_FILE}")

if __name__ == '__main__':
    recall()
