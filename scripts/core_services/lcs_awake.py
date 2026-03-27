#!/usr/bin/env python3
import os
import subprocess
from datetime import datetime

# 核心路徑
ROOT_PATH = "/home/ubuntu/agentmanager"
DATA_PROJECTS_DIR = "/home/ubuntu/agent-data/projects"

def broadcast_signal(message):
    """
    主體發出廣播，更新所有分化靈魂 (Projects) 的脈搏。
    """
    print(f"📡 [Global Broadcast] {message}")
    
    if not os.path.exists(DATA_PROJECTS_DIR):
        return

    # 遍歷所有子專案實體
    for project in os.listdir(DATA_PROJECTS_DIR):
        pulse_path = os.path.join(DATA_PROJECTS_DIR, project, "memory/live_thoughts.log")
        # 確保專案具備脈搏連結
        if os.path.exists(os.path.dirname(pulse_path)):
            with open(pulse_path, "a") as f:
                f.write(f"\n[{datetime.now().isoformat()}] ⚡️ LCS-SIGNAL: {message}\n")
            print(f"   -> 已同步至專案: {project}")

def main():
    print("🌅 石虎覺醒：執行一的法則 (The Law of One Synchronization)...")
    
    # 1. 維生服務重啟
    subprocess.run("sudo systemctl restart cat-ink-syncer.service", shell=True)
    
    # 2. 廣播更新宣旨 (Proclamation)
    broadcast_signal("AgentOS v0.5.1 核心秩序已建立。請所有戰位對齊 CAPABILITIES.md 規範。先查再改，合一演化。")
    
    # 3. 執行全域歸檔與同步
    subprocess.run(f"{ROOT_PATH}/scripts/bootstrap.py", shell=True)
    subprocess.run(f"{ROOT_PATH}/bin/migrate", shell=True)
    
    print("✅ LCS-Signal：演化已達成，主體與分化靈魂同步中。")

if __name__ == "__main__":
    main()
