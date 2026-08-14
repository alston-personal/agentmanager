#!/usr/bin/env python3
"""
ecosystem_report.py
Generates a daily ecosystem health report using Gemini API and sends it to Telegram.
Aggregates tasks executed by the Lobster Engine in the last 24 hours.
"""
import os
import re
import sys
import json
import logging
import requests
import time
from pathlib import Path
from datetime import datetime, timezone, timedelta

# Setup agent_core
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from agent_core.platform import get_platform_driver

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] (EcosystemReport) %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("/home/ubuntu/agent-data/logs/ecosystem_report.log", encoding="utf-8")
    ]
)
logger = logging.getLogger("EcosystemReport")

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

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID")

def get_recent_task_logs(hours: int = 24) -> list[dict]:
    """讀取過去 24 小時內發生的所有任務日誌"""
    log_dir = Path("/home/ubuntu/agent-data/logs/tasks")
    if not log_dir.exists():
        return []
        
    now_ts = time.time()
    recent_logs = []
    
    for f in log_dir.iterdir():
        if not f.is_file() or f.name.startswith("."):
            continue
        mtime = f.stat().st_mtime
        if now_ts - mtime <= hours * 3600:
            try:
                content = f.read_text(encoding="utf-8")
                
                # 判斷任務狀態
                status = "PASS"
                exit_code_match = re.search(r"Exit Code:\s+(-?\d+)", content)
                if exit_code_match:
                    code = int(exit_code_match.group(1))
                    status = "PASS" if code == 0 else "FAIL"
                
                if "TIMEOUT" in content or "Timeout" in content:
                    status = "TIMEOUT"
                elif "BLOCKED" in content:
                    status = "BLOCKED"
                
                # 從檔名解析專案名稱: {timestamp}_{proj_name}_{slug}.log
                parts = f.name.split("_", 2)
                proj_name = parts[1] if len(parts) >= 3 else "unknown"
                
                task_match = re.search(r"Task:\s+(.+)", content)
                task_text = task_match.group(1).strip() if task_match else f.name
                
                recent_logs.append({
                    "timestamp": datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S"),
                    "project": proj_name,
                    "task": task_text,
                    "status": status,
                    "filename": f.name
                })
            except Exception as e:
                logger.warning(f"無法解析任務日誌檔 {f.name}: {e}")
                
    # 依時間由新到舊排序
    recent_logs.sort(key=lambda x: x["timestamp"], reverse=True)
    return recent_logs

def generate_report(pulse_data: dict, task_logs: list) -> str:
    import google.generativeai as genai
    genai.configure(api_key=GEMINI_API_KEY)
    
    # 格式化過去 24 小時任務日誌
    if task_logs:
        tasks_summary = []
        for log in task_logs:
            emoji = {"PASS": "🟢", "FAIL": "🔴", "TIMEOUT": "⏰", "BLOCKED": "🚫"}.get(log["status"], "⚪")
            tasks_summary.append(f"- {emoji} `[{log['timestamp']}]` **{log['project']}** | 任務: {log['task']} ({log['status']})")
        tasks_summary_str = "\n".join(tasks_summary)
    else:
        tasks_summary_str = "*過去 24 小時無任何背景執行任務。*"
        
    prompt = f"""
You are the AgentOS High Commander AI.
Your task is to analyze the daily `pulse.json` snapshot of all 20+ AI projects and the execution log of background tasks performed in the last 24 hours, and generate a concise, executive summary for the human Commander.

Ecosystem pulse snapshot:
{json.dumps(pulse_data, indent=2, ensure_ascii=False)}

Background tasks executed in the last 24 hours:
{tasks_summary_str}

Report Requirements (Must be in Traditional Chinese / Markdown):
1. **Title**: 🌟 AgentOS 每日生態系與任務報告 (Date)
2. **Health Score**: Give an overall health score (0-100) based on active vs stalled/blocked projects.
3. **Executive Summary**: 1-2 paragraphs summarizing the overall state of the ecosystem and the progress of the background execution queue yesterday.
4. **Highlights & Task Summary**:
   - 🟢 Completed / Passed Tasks (briefly summarize notable progress)
   - 🚨 Blocked/Critical/Failed Tasks (Focus here! List any tasks that failed, timed out, or are blocked, referencing which projects need attention).
5. **Actionable Advice**: 1-2 bullet points on what the human should check or fix today.

Keep it highly readable, visually appealing with emojis, and straight to the point.
"""
    model = genai.GenerativeModel('gemini-2.5-flash')
    response = model.generate_content(prompt)
    return response.text

def send_telegram(message: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHANNEL_ID:
        logger.error("Telegram credentials missing.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHANNEL_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        res = requests.post(url, json=payload, timeout=10)
        res.raise_for_status()
        logger.info("✅ Telegram report sent successfully with Markdown formatting.")
    except Exception as e:
        logger.warning(f"⚠️ Failed to send Telegram message with Markdown: {e}. Retrying in plain text mode...")
        payload_fallback = {
            "chat_id": TELEGRAM_CHANNEL_ID,
            "text": message
        }
        try:
            res = requests.post(url, json=payload_fallback, timeout=10)
            res.raise_for_status()
            logger.info("✅ Telegram report sent successfully in plain text mode.")
        except Exception as ex:
            logger.error(f"❌ Failed to send Telegram message in plain text mode: {ex}")

def main():
    if not GEMINI_API_KEY:
        logger.error("GEMINI_API_KEY missing.")
        return
        
    # 時間與次數控制：每天早上 9:00 (含之後) 發送一次日誌
    now_local = datetime.now()
    if now_local.hour < 9:
        logger.info(f"當前時間為 {now_local.strftime('%H:%M')}，未達早上 09:00。跳過發送。")
        return
        
    driver = get_platform_driver(project_root=PROJECT_ROOT)
    
    # 檢查今天是否已發送過報告
    last_report_file = driver.persistent_state_dir() / "last_report_date.txt"
    today_str = now_local.strftime("%Y-%m-%d")
    if last_report_file.exists():
        if last_report_file.read_text(encoding="utf-8").strip() == today_str:
            logger.info("今日每日任務報告已於早前發送。跳過。")
            return
            
    snapshot_file = driver.persistent_state_dir() / "projects_pulse_snapshot.json"
    if not snapshot_file.exists():
        logger.error(f"Snapshot file not found: {snapshot_file}")
        return
        
    try:
        data = json.loads(snapshot_file.read_text(encoding="utf-8"))
    except Exception as e:
        logger.error(f"Failed to read snapshot file: {e}")
        return
        
    logger.info("📁 讀取過去 24 小時的背景執行日誌...")
    task_logs = get_recent_task_logs(hours=24)
    
    logger.info("🧠 Generating ecosystem report via Gemini...")
    report_md = generate_report(data, task_logs)
    
    # 儲存報告檔案供日後查閱
    report_dir = Path("/home/ubuntu/agent-data/journals/ecosystem_reports")
    report_dir.mkdir(parents=True, exist_ok=True)
    report_file = report_dir / f"{today_str}_ecosystem_report.md"
    try:
        report_file.write_text(report_md, encoding="utf-8")
        logger.info(f"💾 每日報告已存檔: {report_file}")
    except Exception as e:
        logger.error(f"❌ 儲存每日報告檔案失敗: {e}")
        
    logger.info("📡 Sending report to Telegram...")
    send_telegram(report_md)
    
    # 標記今日已完成發送
    try:
        last_report_file.write_text(today_str, encoding="utf-8")
        logger.info(f"✅ 每日報告發送狀態已鎖定為今日 ({today_str})")
    except Exception as e:
        logger.error(f"無法寫入 last_report_date.txt: {e}")

if __name__ == "__main__":
    main()
