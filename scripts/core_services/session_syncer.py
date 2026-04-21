#!/usr/bin/env python3
import os
import shutil
import time
import logging
import json
import sys
from pathlib import Path

# Add logic root to path to import service_utils
LOGIC_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(LOGIC_ROOT))
from scripts.service_utils import setup_locking, handle_signals, init_service_logging

def load_env_file(path):
    if not path.exists():
        return
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), os.path.expandvars(value.strip().strip('"').strip("'")))

load_env_file(LOGIC_ROOT / ".env")

# --- 配置 ---
HOME = Path.home()
AGENT_DATA_ROOT = Path(
    os.environ.get("AGENT_DATA_ROOT")
    or os.environ.get("AGENT_DATA_DIR")
    or HOME / "agent-data"
).expanduser()
ANTIGRAVITY_DIR = Path(
    os.environ.get("ANTIGRAVITY_DIR")
    or HOME / ".gemini" / "antigravity"
).expanduser()
BRAIN_DIR = Path(os.environ.get("BRAIN_DIR", ANTIGRAVITY_DIR / "brain")).expanduser()
DATA_DIR = Path(
    os.environ.get(
        "SESSION_SYNC_DIR",
        AGENT_DATA_ROOT / "projects" / "agentmanager" / "logs" / "conversations",
    )
).expanduser()
LOG_FILE = Path(
    os.environ.get(
        "SESSION_SYNC_LOG",
        AGENT_DATA_ROOT / "projects" / "agentmanager" / "logs" / "syncer.log",
    )
).expanduser()
CHECK_INTERVAL = int(os.environ.get("SESSION_SYNC_INTERVAL", "60"))

LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)

logger = init_service_logging(LOG_FILE, "SessionSyncer")

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
    # 確保只有一個實例在運行 (Lock & Replace)
    _lock = setup_locking("session_syncer", replace=True)
    handle_signals()
    
    logger.info("🐾 LeopardCat Session Syncer - Started (PID: %d)", os.getpid())
    while True:
        try:
            sync_conversations()
        except Exception as e:
            logger.error(f"❌ Syncer Error: {str(e)}")
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
