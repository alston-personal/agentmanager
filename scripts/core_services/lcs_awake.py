#!/usr/bin/env python3
import os
import subprocess
import sys

def run_cmd(cmd):
    print(f"📡 LCS-Signal 廣播中: {cmd}")
    try:
        subprocess.run(cmd, shell=True, check=True)
    except subprocess.CalledProcessError as e:
        print(f"🚨 LCS-Signal 攔截報錯: {e}")

def main():
    print("🌅 石虎覺醒：執行全域秩序重建 (LCS-Signal Awakening)...")
    
    # 1. 重啟維生服務
    run_cmd("sudo systemctl restart cat-ink-syncer.service")
    
    # 2. 自動歸檔
    run_cmd("./scripts/bootstrap.py")
    
    # 3. 同步數據層
    run_cmd("./bin/migrate")
    
    print("✅ LCS-Signal：全系統靈魂已歸位。")

if __name__ == "__main__":
    main()
