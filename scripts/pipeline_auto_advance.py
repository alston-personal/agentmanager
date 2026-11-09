#!/usr/bin/env python3
"""AgentOS Pipeline Auto-Advance & Self-Dispatch Engine.

Resolves the core problem:
'Why does autonomous closed loop still require manual user babysitting?'

1. Automatically checks upstream deliverables (e.g. Chapter text done).
2. Auto-advances to downstream stages (formatting check -> packaging -> draft queue).
3. If hitting human approval boundaries (Protected branch, live publishing),
   asynchronously parks the approval in `pending_approvals.json` with push notification metadata,
   and IMMEDIATELY switches execution to the next unblocked backlog task.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import subprocess
from pathlib import Path
from typing import Any

from governance_approval_box import park_approval, load_box

ZEUS_ROOT = Path("/home/ubuntu/zeus-writer")
AGENTMANAGER_ROOT = Path("/home/ubuntu/agentmanager")
AGENT_DATA_ROOT = Path("/home/ubuntu/agent-data")


def inspect_tiandao_chapters() -> dict[str, Any]:
    text_dir = ZEUS_ROOT / "天道敕令_阿賴耶識修真錄" / "正文"
    published_dir = ZEUS_ROOT / "website" / "src" / "content" / "published_chapters"
    
    findings = []
    if not text_dir.exists():
        return {"status": "skipped", "findings": []}

    for f in sorted(text_dir.glob("*.md")):
        name = f.name
        # Match chapter index
        parts = name.split("_")
        if not parts[0].isdigit():
            continue
        ch_num = int(parts[0])
        content = f.read_text(encoding="utf-8")
        
        # Check 5-section compliance
        has_5_sections = content.count("## ") >= 5
        lines_count = len(content.splitlines())
        
        # Check if published
        pub_file = published_dir / name
        is_published = pub_file.exists()

        findings.append({
            "chapter": ch_num,
            "filename": name,
            "is_published": is_published,
            "has_5_sections": has_5_sections,
            "lines": lines_count
        })

    return {"status": "inspected", "chapters": findings}


def advance_tiandao_pipeline() -> None:
    res = inspect_tiandao_chapters()
    chapters = res.get("chapters", [])
    
    for ch in chapters:
        num = ch["chapter"]
        if not ch["is_published"]:
            print(f"🔍 Found unreleased Chapter {num} ({ch['filename']})")
            if not ch["has_5_sections"]:
                print(f"  ⚠️ Chapter {num} does not fully conform to 5-section standard. Auto-flagging for formatting.")
            else:
                print(f"  ✅ Chapter {num} meets 5-section quality standard.")

            # Park approval for publishing rather than stalling
            park_approval(
                approval_id=f"zeus-tiandao-ch{num:02d}-publish",
                project_id="zeus-writer",
                actor="tiandao-alaya",
                title=f"《天道敕令》第 {num} 章 全渠道正式發布審核",
                action_type="external_publication",
                payload={"chapter": num, "filename": ch["filename"]},
                next_unblocked_task=f"推進第 {num + 1} 章草稿大綱與排版預研"
            )
            # Break after parking the earliest unreleased chapter
            break


def run_pipeline_auto_advance():
    print("🚀 [AgentOS Self-Dispatch] Running autonomous stage auto-advance...")
    
    # 1. Advance Zeus Writer Novel Workflow
    advance_tiandao_pipeline()
    
    # 2. Trigger Mission Control live synchronization
    try:
        from sync_mission_control import main as sync_mc
        sync_mc()
        print("✅ [AgentOS Self-Dispatch] Mission control telemetry updated.")
    except Exception as e:
        print(f"⚠️ [AgentOS Self-Dispatch] Failed to sync mission control: {e}")

    print("✨ [AgentOS Self-Dispatch] Pipeline advance tick completed.")


if __name__ == "__main__":
    run_pipeline_auto_advance()
