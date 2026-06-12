#!/usr/bin/env python3
"""
ecosystem_report.py
Generates a daily ecosystem health report using Gemini API and sends it to Telegram.
"""
import os
import sys
import json
import logging
import requests
from pathlib import Path
from datetime import datetime, timezone

# Setup agent_core
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from agent_core.platform import get_platform_driver

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
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

def generate_report(pulse_data: dict) -> str:
    import google.generativeai as genai
    genai.configure(api_key=GEMINI_API_KEY)
    
    prompt = f"""
You are the AgentOS High Commander AI.
Your task is to analyze the following daily `pulse.json` snapshot of all 20+ AI projects and generate a concise, executive summary for the human Commander.

Data:
{json.dumps(pulse_data, indent=2, ensure_ascii=False)}

Report Requirements (Must be in Traditional Chinese / Markdown):
1. **Title**: 🌟 AgentOS 每日生態系報告 (Date)
2. **Health Score**: Give an overall health score (0-100) based on active vs stalled/blocked projects.
3. **Executive Summary**: 1-2 paragraphs summarizing the overall state. Are things running smoothly?
4. **Highlights**:
   - 🟢 Active & Healthy Projects (brief mention of notable ones)
   - 🚨 Blocked/Critical/Stalled Projects (Focus here! Explicitly list them and their last_status if they have errors or are skipped/blocked).
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
        logger.info("✅ Telegram report sent successfully.")
    except Exception as e:
        logger.error(f"❌ Failed to send Telegram message: {e}")

def main():
    if not GEMINI_API_KEY:
        logger.error("GEMINI_API_KEY missing.")
        return
        
    driver = get_platform_driver(project_root=PROJECT_ROOT)
    snapshot_file = driver.persistent_state_dir() / "projects_pulse_snapshot.json"
    
    if not snapshot_file.exists():
        logger.error(f"Snapshot file not found: {snapshot_file}")
        return
        
    try:
        data = json.loads(snapshot_file.read_text(encoding="utf-8"))
    except Exception as e:
        logger.error(f"Failed to read snapshot file: {e}")
        return
        
    logger.info("🧠 Generating ecosystem report via Gemini...")
    report_md = generate_report(data)
    
    logger.info("📡 Sending report to Telegram...")
    send_telegram(report_md)

if __name__ == "__main__":
    main()
