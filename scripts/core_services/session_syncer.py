#!/usr/bin/env python3
import os
import shutil
import time
import logging
from pathlib import Path
import json

# --- 配置 ---
BRAIN_DIR = Path("/home/ubuntu/.gemini/antigravity/brain")
DATA_DIR = Path("/home/ubuntu/agent-data/projects/agentmanager/logs/conversations")
CHECK_INTERVAL = 60  # 每 60 秒同步一次

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler("/home/ubuntu/agent-data/projects/agentmanager/logs/syncer.log"),
        logging.StreamHandler()
    ]
)

def sync_conversations():
    """ 掃描 .brain 目錄並將有內容的 JSON 資料備份到數據層 """
    if not BRAIN_DIR.exists():
        logging.warning(f"Brain directory {BRAIN_DIR} not found.")
        return

    # 巡視所有對話資料夾 (GUID)
    for entry in BRAIN_DIR.iterdir():
        if entry.is_dir():
            # 我們要對整個目錄做同步 (包含 .system_generated/logs 如果存在)
            target_entry_dir = DATA_DIR / entry.name
            
            # 如果目錄非空，執行備份
            if any(entry.iterdir()):
                if not target_entry_dir.exists():
                    target_entry_dir.mkdir(parents=True, exist_ok=True)
                
                # 同步內容 (使用 rsync 或簡單的 cp -r)
                # 這裡使用簡單的 shutil.copytree 或 manual copy
                for item in entry.glob('**/*'):
                    if item.is_file():
                        relative_path = item.relative_to(entry)
                        dest_path = target_entry_dir / relative_path
                        
                        # 只有在發生變化時才覆蓋
                        if not dest_path.exists() or item.stat().st_mtime > dest_path.stat().st_mtime:
                            dest_path.parent.mkdir(parents=True, exist_ok=True)
                            shutil.copy2(item, dest_path)
                            logging.info(f"✅ Synced: {entry.name}/{relative_path}")

def main():
    logging.info("🐾 LeopardCat Session Syncer - Started")
    while True:
        try:
            sync_conversations()
        except Exception as e:
            logging.error(f"❌ Syncer Error: {str(e)}")
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
