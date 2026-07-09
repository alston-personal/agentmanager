#!/usr/bin/env python3
"""
Antigravity Chronos Central Scheduler
Loads periodic jobs defined in schedule.yaml and coordinates their execution
under a single process thread to maximize performance and reliability.
"""
import os
import sys
import time
import yaml
import logging
import subprocess
from pathlib import Path
from datetime import datetime, timezone

# Get the script's root directory dynamically (scripts/chronos.py -> root is scripts/..)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "schedule.yaml"

# Determine data root dynamically from environment or fallback to home directory
DATA_ROOT_ENV = os.getenv("AGENT_DATA_ROOT") or os.getenv("AGENT_DATA_DIR")
if DATA_ROOT_ENV:
    DATA_ROOT = Path(DATA_ROOT_ENV).expanduser()
else:
    DATA_ROOT = Path.home() / "agent-data"

log_dir = DATA_ROOT / "logs"
log_dir.mkdir(parents=True, exist_ok=True)
log_file = log_dir / "chronos.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] (Chronos) %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_file, encoding="utf-8")
    ]
)
logger = logging.getLogger("Chronos")

def load_schedule():
    if not CONFIG_PATH.exists():
        logger.error(f"Configuration file not found @ {CONFIG_PATH}")
        return []
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            return data.get("schedules", [])
    except Exception as e:
        logger.error(f"Failed to parse schedule.yaml: {e}")
        return []

def run_job(name: str, command: str):
    logger.info(f"🚀 [Trigger] Launching job '{name}': {command}")
    try:
        # Run in background to avoid blocking the main scheduler thread
        subprocess.Popen(
            command,
            shell=True,
            cwd=str(PROJECT_ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    except Exception as e:
        logger.error(f"❌ Failed to spawn job '{name}': {e}")

def main():
    logger.info("⏳ Chronos Scheduler starting...")
    jobs = load_schedule()
    if not jobs:
        logger.error("No active schedules loaded. Exiting.")
        return 1
        
    logger.info(f"Loaded {len(jobs)} scheduled tasks:")
    for job in jobs:
        logger.info(f"  - {job['name']} (every {job['interval_seconds']}s): {job['command']}")
        job["last_run"] = 0 # Forces immediate execution on startup for heartbeat and watchdog

    while True:
        try:
            now = time.time()
            for job in jobs:
                if now - job["last_run"] >= job["interval_seconds"]:
                    job["last_run"] = now
                    run_job(job["name"], job["command"])
        except KeyboardInterrupt:
            logger.info("🛑 Chronos Scheduler stopped by operator.")
            break
        except Exception as e:
            logger.error(f"Error in scheduler main loop: {e}")
            
        time.sleep(5) # Small sleep window

import argparse
import re

# 專案名稱與實際邏輯路徑對照表
PROJECT_MAP = {
    "moltbot": str(Path.home() / "moltbot"),
    "openclaw": str(Path.home() / "openclaw"),
    "agentmanager": str(PROJECT_ROOT),
    "leopardcat-tarot": str(Path.home() / "leopardcat-tarot"),
    "zeus-writer": str(Path.home() / "zeus-writer"),
    "youtube-ai-manager": str(Path.home() / "youtube-ai-manager"),
    "y2helper": str(Path.home() / "y2helper"),
    "beauty-pk": str(Path.home() / "beauty-pk")
}

def load_env():
    env_path = PROJECT_ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))

load_env()

def send_telegram_alert(message: str, project_name: str = None, interactive: bool = False):
    import requests
    logger.info(f"🚨 [Self-Pushing] 嘗試發送 Telegram 通知...")
    payload = {"message": message}
    if project_name:
        payload["project_name"] = project_name
    if interactive:
        payload["interactive"] = True
    
    # Method 1: 本地 HTTP Bridge 警報端點 (由 tg_bridge.py 提供，Port 8085)
    try:
        res = requests.post("http://127.0.0.1:8085/alert", json=payload, timeout=5)
        if res.status_code == 200:
            logger.info("✅ 成功透過本地 HTTP Bridge 發送通知。")
            return True
    except Exception as e:
        logger.warning(f"⚠️ 本地 HTTP Bridge 無法存取: {e}。改用直接呼叫 Telegram API 備援...")

    # Method 2: 直接呼叫 Telegram API 備援
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TG_BOT_SUNLAKE_CC_TOKEN")
    channel_id = os.getenv("TELEGRAM_CHANNEL_ID")
    if bot_token and channel_id:
        try:
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            direct_payload = {
                "chat_id": channel_id,
                "text": f"⚠️ **[AgentOS 備援通知]**\n\n{message}",
                "parse_mode": "Markdown"
            }
            res = requests.post(url, json=direct_payload, timeout=10)
            if res.status_code == 200:
                logger.info("✅ 成功透過 Telegram API 直接發送通知。")
                return True
            else:
                logger.error(f"❌ Telegram API 回傳錯誤: {res.text}")
        except Exception as ex:
            logger.error(f"❌ Telegram API 直接呼叫失敗: {ex}")
    else:
        logger.error("❌ 無法發送通知：環境變數中缺少 Telegram 憑證。")
    return False

def check_project_git_changes(logic_dir: str):
    """
    檢查專案邏輯目錄中的最新 Git Commit。
    若該 Commit 於過去 30 分鐘內建立，則回傳 (commit_hash, commit_msg, diff_stat)。
    """
    try:
        git_dir = Path(logic_dir) / ".git"
        if not git_dir.exists():
            return None
            
        cmd_log = "git log -n 1 --pretty=format:'%h|%B|%ct'"
        res = subprocess.run(cmd_log, shell=True, cwd=logic_dir, capture_output=True, text=True, timeout=10)
        if res.returncode != 0 or not res.stdout.strip():
            return None
            
        parts = res.stdout.strip().split('|', 2)
        if len(parts) < 3:
            return None
            
        commit_hash, commit_msg, commit_time_str = parts[0], parts[1].strip(), parts[2].strip()
        commit_time = int(commit_time_str)
        
        # 如果是過去 30 分鐘 (1800 秒) 內建立的 Commit
        if time.time() - commit_time < 1800:
            cmd_diff = "git diff --stat HEAD~1 HEAD"
            res_diff = subprocess.run(cmd_diff, shell=True, cwd=logic_dir, capture_output=True, text=True, timeout=10)
            diff_stat = res_diff.stdout.strip() if res_diff.returncode == 0 else ""
            return commit_hash, commit_msg, diff_stat
    except Exception as e:
        logger.error(f"檢查 {logic_dir} 的 Git 變更時發生錯誤: {e}")
    return None

def check_project_autonomous_error(status_path: Path):
    """
    檢查 STATUS.md 中是否有主動記錄的自治推進異常報告 (🔴)。
    """
    try:
        if not status_path.exists():
            return None
        content = status_path.read_text(encoding="utf-8")
        if "自治推進異常報告" in content or "🔴 自治推進" in content:
            lines = content.splitlines()
            error_lines = []
            capture = False
            for line in lines:
                if "自治推進異常報告" in line or "🔴 自治推進" in line:
                    capture = True
                    error_lines.append(line)
                    continue
                if capture:
                    if line.startswith("#") and not line.startswith("###"):
                        break
                    if len(error_lines) > 12:
                        break
                    error_lines.append(line)
            if error_lines:
                return "\n".join(error_lines).strip()
    except Exception as e:
        logger.error(f"從 {status_path} 讀取自治異常報告時發生錯誤: {e}")
    return None

def scan_stagnant_projects(dry_run=False):
    """
    掃描所有在 agent-data 的專案狀態，尋找停滯的專案。
    """
    logger.info("🔍 [Self-Pushing] 啟動停滯專案掃描探針...")
    projects_dir = DATA_ROOT / "projects"
    if not projects_dir.exists():
        logger.error(f"Projects directory not found @ {projects_dir}")
        return []
        
    stagnant_projects = []
    for proj_path in projects_dir.iterdir():
        if not proj_path.is_dir():
            continue
            
        proj_name = proj_path.name
        status_file = proj_path / "STATUS.md"
        if not status_file.exists():
            continue
            
        # 讀取 STATUS.md 內容
        try:
            with open(status_file, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            logger.error(f"Failed to read STATUS.md for {proj_name}: {e}")
            continue
            
        # 尋找未完成的任務 [ ]
        undone_tasks = re.findall(r"-\s*\[\s*\]\s*(.*)", content)
        
        # 檢查專案最後修改時間
        mtime = status_file.stat().st_mtime
        stagnant_seconds = time.time() - mtime
        stagnant_days = stagnant_seconds / 86400
        
        logger.info(f"Project '{proj_name}': {len(undone_tasks)} undone tasks, last updated {stagnant_days:.2f} days ago.")
        
        # 停滯標準：只要有未完成待辦，且超過 1.0 天沒有修改（乾跑或測試時放寬）
        is_stagnant = (stagnant_days >= 1.0) or (len(undone_tasks) > 0 and dry_run)
        
        if len(undone_tasks) > 0 and is_stagnant:
            if proj_name in PROJECT_MAP:
                stagnant_projects.append({
                    "name": proj_name,
                    "logic_dir": PROJECT_MAP[proj_name],
                    "undone_count": len(undone_tasks),
                    "status_path": status_file
                })
                logger.info(f"🚩 專案 '{proj_name}' 被判定為停滯專案，需要自治推進！")
            else:
                logger.warning(f"⚠️ 專案 '{proj_name}' 有待辦任務但未對應邏輯路徑，跳過。")
                
    return stagnant_projects

def run_self_pushing(dry_run=False):
    """
    執行自主推進專案主邏輯
    """
    stagnant_projects = scan_stagnant_projects(dry_run)
    if not stagnant_projects:
        logger.info("✅ 沒有偵測到任何需要自治推進的停滯專案！")
        return
    logger.info(f"🚀 準備對 {len(stagnant_projects)} 個專案執行自治推進...")
    prompt_template_path = PROJECT_ROOT / "templates/self_pushing_prompt.txt"
    if not prompt_template_path.exists():
        logger.error(f"Prompt template not found @ {prompt_template_path}")
        return
        
    with open(prompt_template_path, "r", encoding="utf-8") as f:
        prompt_template = f.read()
        
    for proj in stagnant_projects:
        name = proj["name"]
        logic_dir = proj["logic_dir"]
        status_path = proj["status_path"]
        logger.info(f"🤖 [Autonomous] 開始推進專案 '{name}'，路徑為 '{logic_dir}'")
        
        custom_message = prompt_template.replace("【專案名稱】", name)
        
        if dry_run:
            logger.info(f"  Command: pnpm --dir {Path.home()}/openclaw openclaw agent --agent main --model ollama/gemma2:2b --thinking off (cwd={logic_dir})")
            logger.info(f"  Message length: {len(custom_message)} chars")
            continue
            
        try:
            logger.info(f"🔥 [Branch-Gating] 準備為專案 '{name}' 建立並隔離至主題分支 agent/auto-pushing...")
            # 1. 確保在 main 並拉取最新代碼
            subprocess.run("git checkout main && git pull --rebase", shell=True, cwd=logic_dir, capture_output=True)
            # 2. 強制重設/建立主題分支指向最新的 main
            subprocess.run("git checkout -B agent/auto-pushing main", shell=True, cwd=logic_dir, capture_output=True)

            logger.info(f"🔥 啟動 OpenClaw 自主代理 (指定本機 Gemma2 路由)，執行專案 '{name}' 自治推進循環...")
            
            # 使用本機 Gemma2 路由，完全免費免 Token 額度
            # 將 cwd 設為 logic_dir 以自動判定 Workspace，並使用 pnpm --dir 來定位 openclaw 執行檔，移除不合法的 --workspace-dir，並將 --thinking 設為 off (Gemma 不支援 reasoning)
            process = subprocess.run(
                ["pnpm", "--dir", str(Path.home() / "openclaw"), "openclaw", "agent", "--agent", "main", "--message", custom_message, "--model", "ollama/gemma2:2b", "--thinking", "off"],
                cwd=logic_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=1200
            )
            
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            if process.returncode == 0:
                logger.info(f"✅ OpenClaw 自主代理執行成功退出 (Exit 0)。開始盤點推進成果...")
                
                # 1. 在隔離分支中檢查是否有最新的 Git Commit
                git_info = check_project_git_changes(logic_dir)
                
                # 2. 檢查 STATUS.md 是否有異常 (優雅降級時會寫入)
                auton_err = check_project_autonomous_error(status_path)
                
                # 3. 收集完資料後，立即將邏輯庫切回 main，保持工作區乾淨安全
                subprocess.run("git checkout main -f", shell=True, cwd=logic_dir, capture_output=True)
                
                if auton_err:
                    logger.warning(f"⚠️ 專案 '{name}' 雖然執行退出，但在 STATUS.md 中發現自治異常報告！")
                    send_telegram_alert(
                        f"🔴 **專案自主推進中止 (需要人工介入)**\n\n"
                        f"🔹 **專案**: `{name}`\n"
                        f"🔹 **異常報告**:\n{auton_err}\n\n"
                        f"🔹 **時間**: `{timestamp}`",
                        project_name=name,
                        interactive=False
                    )
                elif git_info:
                    commit_hash, commit_msg, diff_stat = git_info
                    logger.info(f"🎉 專案 '{name}' 自治推進成功！已建立隔離變更: {commit_hash}，等待 Operator 核准...")
                    send_telegram_alert(
                        f"🤖 **專案自主變更已完成 (等待您的核准)**\n\n"
                        f"🔹 **專案**: `{name}`\n"
                        f"🔹 **成果摘要**: `{commit_msg}` (Commit: `{commit_hash}`)\n"
                        f"🔹 **隔離分支**: `agent/auto-pushing`\n"
                        f"🔹 **變更檔案列表**:\n```\n{diff_stat}\n```\n"
                        f"🔹 **說明**: 變更已安全鎖定於本地主題分支，請使用下方按鈕進行審查與合併。\n"
                        f"🔹 **時間**: `{timestamp}`",
                        project_name=name,
                        interactive=True # 啟用一鍵核准/捨棄按鈕！
                    )
                else:
                    logger.info(f"ℹ️ 專案 '{name}' 執行退出，但未偵測到 Git 異動或異常記錄。")
                    send_telegram_alert(
                        f"🤖 **專案自主推進完成 (無變更)**\n\n"
                        f"🔹 **專案**: `{name}`\n"
                        f"🔹 **狀態**: 代理成功執行，但可能無待辦需要處理或未產生代碼變更。\n"
                        f"🔹 **時間**: `{timestamp}`",
                        project_name=name,
                        interactive=False
                    )
            else:
                logger.error(f"❌ OpenClaw 進程執行異常退出，Exit Code: {process.returncode}")
                # 擷取最後 10 行錯誤日誌
                stderr_excerpt = "\n".join(process.stderr.splitlines()[-10:]) if process.stderr else "無錯誤輸出"
                # 執行退出失敗也切回 main 確保不殘留在錯亂分支
                subprocess.run("git checkout main -f", shell=True, cwd=logic_dir, capture_output=True)
                send_telegram_alert(
                    f"💥 **專案自主推進執行失敗**\n\n"
                    f"🔹 **專案**: `{name}`\n"
                    f"🔹 **Exit Code**: `{process.returncode}`\n"
                    f"🔹 **錯誤輸出**:\n```\n{stderr_excerpt}\n```\n"
                    f"🔹 **時間**: `{timestamp}`",
                    project_name=name,
                    interactive=False
                )
        except subprocess.TimeoutExpired:
            logger.error(f"❌ 專案 '{name}' 自治推進超時 (20 分鐘)")
            send_telegram_alert(
                f"⏰ **專案自主推進執行超時 (20m)**\n\n"
                f"🔹 **專案**: `{name}`\n"
                f"🔹 **說明**: 代理執行超過 20 分鐘保護閾值，已自動強制中止。\n"
                f"🔹 **時間**: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`"
            )
        except Exception as e:
            logger.error(f"❌ 呼叫 OpenClaw 失敗: {e}")
            send_telegram_alert(
                f"💥 **專案自主推進系統異常**\n\n"
                f"🔹 **專案**: `{name}`\n"
                f"🔹 **錯誤資訊**: `{e}`\n"
                f"🔹 **時間**: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`"
            )

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Chronos Central Scheduler")
    parser.add_argument("--self-pushing", action="store_true", help="Trigger autonomous loop for stagnant projects")
    parser.add_argument("--dry-run-self-pushing", action="store_true", help="Dry-run scan and print stagnant projects")
    args = parser.parse_args()
    
    if args.self_pushing:
        run_self_pushing(dry_run=False)
    elif args.dry_run_self_pushing:
        run_self_pushing(dry_run=True)
    else:
        sys.exit(main())
