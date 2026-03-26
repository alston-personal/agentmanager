#!/usr/bin/env python3
"""
scripts/batch_report_sync.py
Spawns background processes to formally `/report` and sync all projects
with 'unknown' or 'stale' health into the new system.
"""
import sys
import os
import subprocess

# Ensure we can import agent_core
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from agent_core.project_store import list_projects

def main():
    projects = list_projects()
    
    # 找出所有尚未同步過（unknown）或是過時（stale）的專案
    targets = [p for p in projects if p.health.freshness in ("unknown", "stale")]
    
    print(f"啟動批次同步任務：預計處理 {len(targets)} 個專案...")
    
    for project in targets:
        print(f"🚀 發起 process: 同步 [{project.project_id}]...")
        
        # 呼叫新的 cli entrypoint
        cmd = [
            "python3", "cli/run_workflow.py", "report",
            "--project", project.project_id,
            "--summary", "System Auto-Sync: Migrating to new formal session & schema",
            "--notes", "Zero-Trust default state closed by system pulse."
        ]
        
        # 這裡用 subprocess 啟動獨立的 process
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            if result.returncode == 0:
                print(f"  ✅ 成功")
            else:
                print(f"  ❌ 失敗: {result.stderr.strip()}")
        except Exception as e:
            print(f"  ⚠️ 錯誤: {e}")

    print("\n🎉 全部處理完畢！可使用 `/status` 重新檢查狀態。")

if __name__ == "__main__":
    main()
