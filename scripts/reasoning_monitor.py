#!/usr/bin/env python3
"""
📊 AgentOS LLM 決策與推理審計檢視器 (LLM Reasoning Audit Trail Viewer)
用於檢視各角色何時呼叫了 LLM、使用了哪個模型、做出了何種判斷與代碼改變。
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

DATA_ROOT = Path(os.environ.get("AGENT_DATA_ROOT", "/home/ubuntu/agent-data"))
AUDIT_FILE = DATA_ROOT / "runtime" / "llm_reasoning" / "reasoning_audit_ledger.jsonl"


def show_audit(limit: int = 10, role_filter: str | None = None):
    if not AUDIT_FILE.exists():
        print("ℹ️ 尚無 LLM 推理審計記錄 (檔案尚未產生)。")
        return

    entries = []
    with open(AUDIT_FILE, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try:
                    entries.append(json.loads(line))
                except Exception:
                    pass

    if role_filter:
        entries = [e for e in entries if e.get("role_id") == role_filter]

    print(f"\n🧠 【AgentOS 角色 LLM 決策審計台帳】(最近 {min(len(entries), limit)} 筆 / 總計 {len(entries)} 筆)")
    print("=" * 80)
    for idx, e in enumerate(reversed(entries[-limit:]), 1):
        ts = e.get("timestamp", "N/A")
        role = e.get("role_id", "unknown")
        proj = e.get("project_id") or "全系統/無特定"
        prov = e.get("provider", "unknown")
        status = e.get("status", "unknown")
        prompt = e.get("prompt_summary", "")
        decision = e.get("decision_preview", "")

        print(f"[{idx}] ⏰ 時間: {ts}")
        print(f"    👤 角色: {role} | 🎯 目標專案: {proj} | 🤖 驅動模型: {prov} ({status})")
        print(f"    📝 遭遇情境 / 任務: {prompt}")
        print(f"    💡 LLM 裁決與改變: {decision}")
        print("-" * 80)


if __name__ == "__main__":
    limit = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 10
    role = sys.argv[2] if len(sys.argv) > 2 else None
    show_audit(limit, role)
