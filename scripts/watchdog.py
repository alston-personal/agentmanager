#!/usr/bin/env python3
import os
import subprocess
import requests
import logging
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def load_env_file(path: Path):
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), os.path.expandvars(value.strip().strip('"').strip("'")))


load_env_file(PROJECT_ROOT / ".env")

# Load environment variables
AGENT_DATA_ROOT = os.getenv("AGENT_DATA_ROOT", "/home/ubuntu/agent-data")
AGENT_MODE = os.getenv("AGENT_MODE", "CLIENT")
SYNC_LOG_PATH = os.path.join(AGENT_DATA_ROOT, "memory", "session_sync.md")
N8N_URL = os.getenv("N8N_URL")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Watchdog")

if AGENT_MODE != "CORE":
    # On non-core machines, watchdog should be silent or limited
    # But for now, we just exit to prevent fighting over services
    print(f"Watchdog: AGENT_MODE is {AGENT_MODE}. Skipping core service management.")
    import sys
    sys.exit(0)

def auto_pull_logic():
    """CORE 機器自動同步邏輯層 (agentmanager) 代碼"""
    try:
        project_root = os.getenv("AGENT_PROJECT_ROOT", "/home/ubuntu/agentmanager")
        os.chdir(project_root)
        # 只有在 Git 目錄下才執行
        if os.path.exists(".git"):
            logger.info("📡 [Sync] Core Pulling latest logic...")
            subprocess.run(["git", "pull", "--rebase"], capture_output=True)
    except Exception as e:
        logger.error(f"Auto-pull failed: {e}")

def log_to_sync(message: str):
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    os.makedirs(os.path.dirname(SYNC_LOG_PATH), exist_ok=True)
    with open(SYNC_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(f"\n> [!WARNING]\n> **Watchdog @ {timestamp}**: {message}\n")

def check_systemd_user(service_name: str) -> bool:
    try:
        env = os.environ.copy()
        if "XDG_RUNTIME_DIR" not in env:
            env["XDG_RUNTIME_DIR"] = f"/run/user/{os.getuid()}"
        result = subprocess.run(
            ["systemctl", "--user", "is-active", service_name],
            capture_output=True, text=True, env=env
        )
        return result.stdout.strip() == "active"
    except Exception as e:
        logger.error(f"Failed to check systemd service {service_name}: {e}")
        return False

def restart_systemd_user(service_name: str):
    logger.warning(f"Attempting to restart {service_name}...")
    env = os.environ.copy()
    if "XDG_RUNTIME_DIR" not in env:
        env["XDG_RUNTIME_DIR"] = f"/run/user/{os.getuid()}"
    subprocess.run(["systemctl", "--user", "restart", service_name], env=env)
    log_to_sync(f"Service `{service_name}` was down. Attempted restart.")

def check_http(url: str) -> bool:
    if not url: return True # Skip if no URL
    try:
        import requests
        response = requests.get(url, timeout=5)
        return response.status_code == 200
    except Exception as e:
        logger.error(f"HTTP check failed for {url}: {e}")
        return False

def check_docker_container(container_name: str) -> bool:
    try:
        result = subprocess.run(
            ["sudo", "docker", "inspect", "-f", "{{.State.Running}}", container_name],
            capture_output=True, text=True
        )
        return result.stdout.strip() == "true"
    except Exception as e:
        logger.error(f"Failed to check docker container {container_name}: {e}")
        return False

def restart_docker_container(container_name: str):
    logger.warning(f"Attempting to restart docker container {container_name}...")
    subprocess.run(["sudo", "docker", "start", container_name])
    log_to_sync(f"Docker container `{container_name}` was down. Attempted start.")

def verify_python_deps():
    # Simple check for critical telegram lib
    try:
        import telegram
        return True
    except ImportError:
        logger.error("❌ Critical dependency 'telegram' missing!")
        return False

def main():
    # 📡 自動同步代碼 (只在 CORE 模式)
    auto_pull_logic()

    # 核心 Systemd 服務
    core_services = ["tg-commander.service", "moltbot-gateway.service"]
    
    for svc in core_services:
        is_active = check_systemd_user(svc)
        if not is_active:
            # Special case: check if it's missing dependencies
            if svc == "tg-commander.service" and not verify_python_deps():
                logger.warning("Attempting to repair dependencies for tg-commander...")
                subprocess.run(["/home/ubuntu/agentmanager/.venv/bin/pip", "install", "-r", "/home/ubuntu/agentmanager/requirements.txt"])
            
            restart_systemd_user(svc)
        else:
            logger.info(f"✅ Core service {svc} is active.")

    # Docker 容器狀態
    if not check_docker_container("n8n"):
        logger.error("❌ n8n container is NOT running.")
        restart_docker_container("n8n")
    else:
        logger.info("✅ n8n container is running.")

    # HTTP 健康檢查
    if N8N_URL:
        health_url = f"{N8N_URL.rstrip('/')}/healthz"
        if not check_http(health_url):
            logger.error(f"❌ n8n API is unreachable @ {health_url}")
            log_to_sync(f"n8n API is unreachable at `{health_url}`. Service might be starting or misconfigured.")
        else:
            logger.info("✅ n8n API is healthy.")

if __name__ == "__main__":
    main()
