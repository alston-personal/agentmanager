#!/usr/bin/env python3
import os
import subprocess
import requests
import logging
from datetime import datetime, timezone

# Load environment variables
AGENT_DATA_ROOT = os.getenv("AGENT_DATA_ROOT", "/home/ubuntu/agent-data")
SYNC_LOG_PATH = os.path.join(AGENT_DATA_ROOT, "memory", "session_sync.md")
N8N_URL = os.getenv("N8N_URL")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Watchdog")

def log_to_sync(message: str):
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    with open(SYNC_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(f"\n> [!WARNING]\n> **Watchdog @ {timestamp}**: {message}\n")

def check_systemd_user(service_name: str) -> bool:
    try:
        result = subprocess.run(
            ["systemctl", "--user", "is-active", service_name],
            capture_output=True, text=True
        )
        return result.stdout.strip() == "active"
    except Exception as e:
        logger.error(f"Failed to check systemd service {service_name}: {e}")
        return False

def restart_systemd_user(service_name: str):
    logger.warning(f"Attempting to restart {service_name}...")
    subprocess.run(["systemctl", "--user", "restart", service_name])
    log_to_sync(f"Service `{service_name}` was down. Attempted restart.")

def check_http(url: str) -> bool:
    if not url: return True # Skip if no URL
    try:
        response = requests.get(url, timeout=5)
        return response.status_code == 200
    except Exception as e:
        logger.error(f"HTTP check failed for {url}: {e}")
        return False

def main():
    # 這裡未來應從 SERVICES.md 解析，但目前先硬編碼核心邏輯
    core_services = ["tg-commander.service", "moltbot-gateway.service"]
    
    for svc in core_services:
        if not check_systemd_user(svc):
            restart_systemd_user(svc)
        else:
            logger.info(f"✅ Core service {svc} is active.")

    # Optional n8n check
    if N8N_URL:
        health_url = f"{N8N_URL.rstrip('/')}/healthz"
        if not check_http(health_url):
            logger.error(f"❌ n8n is unreachable @ {health_url}")
            log_to_sync(f"Optional plugin `n8n` is down or unreachable at `{health_url}`.")
        else:
            logger.info("✅ n8n plugin is healthy.")

if __name__ == "__main__":
    main()
