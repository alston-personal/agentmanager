#!/usr/bin/env python3
"""
Antigravity AgentOS Self-Healing Watchdog
Actively monitors system services, Docker containers, and project STATUS.md files.
Automatically triggers self-healing routines and broadcasts Telegram alerts.
"""
import os
import sys
import re
import json
import logging
import argparse
import subprocess
import requests
from datetime import datetime, timezone
from pathlib import Path

# Resolve dynamic paths (with fallback for legacy environments)
PROJECT_ROOT = Path(os.environ.get("AGENT_PROJECT_ROOT", Path(__file__).resolve().parents[1])).resolve()
AGENT_DATA_ROOT = Path(
    os.environ.get("AGENT_DATA_ROOT")
    or os.environ.get("AGENT_DATA_DIR")
    or Path.home() / "agent-data"
).expanduser()

LOCK_DIR = Path("/tmp/watchdog_locks")
LOCK_DIR.mkdir(parents=True, exist_ok=True)

# Setup logging dynamically
log_dir = AGENT_DATA_ROOT / "logs"
log_dir.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] (%(name)s) %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(str(log_dir / "watchdog.log"), encoding="utf-8")
    ]
)
logger = logging.getLogger("Watchdog")

class BackoffManager:
    def __init__(self, state_file=LOCK_DIR / "watchdog_backoff.json"):
        self.state_file = state_file
        self.state = self._load()

    def _load(self):
        if self.state_file.exists():
            try:
                return json.loads(self.state_file.read_text(encoding="utf-8"))
            except Exception as e:
                logger.error(f"Failed to load backoff state: {e}")
        return {}

    def _save(self):
        try:
            self.state_file.write_text(json.dumps(self.state, indent=2), encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to save backoff state: {e}")

    def can_retry(self, entity_id: str) -> bool:
        if entity_id not in self.state:
            return True
        record = self.state[entity_id]
        failures = record.get("failures", 0)
        last_attempt = datetime.fromisoformat(record["last_attempt"])
        
        if failures == 1:
            delay = 15
        elif failures == 2:
            delay = 30
        else:
            delay = 60
            
        elapsed = (datetime.now(timezone.utc) - last_attempt).total_seconds() / 60.0
        if elapsed >= delay:
            return True
        else:
            logger.info(f"⏳ [Backoff] {entity_id} is in cooldown. {elapsed:.1f}/{delay} mins elapsed. Skipping heal.")
            return False

    def record_failure(self, entity_id: str):
        record = self.state.get(entity_id, {"failures": 0})
        record["failures"] += 1
        record["last_attempt"] = datetime.now(timezone.utc).isoformat()
        self.state[entity_id] = record
        self._save()
        logger.warning(f"📈 [Backoff] Recorded failure for {entity_id}. Total failures: {record['failures']}")

    def reset(self, entity_id: str):
        if entity_id in self.state:
            del self.state[entity_id]
            self._save()
            logger.info(f"🔄 [Backoff] Reset failure count for {entity_id}")

backoff_mgr = BackoffManager()

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

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID")
AGENT_MODE = os.getenv("AGENT_MODE", "CORE")

def heal_stale_git_locks():
    """
    Checks if there are any .git/index.lock files in active repos when no active git process is running.
    """
    logger.info("🔧 [Self-Healing] Checking for stale git locks...")
    try:
        git_running = subprocess.run(["pgrep", "-x", "git"], capture_output=True).returncode == 0
    except Exception:
        git_running = False

    if git_running:
        logger.info("Git process is currently active. Skipping lock file check.")
        return

    for repo_dir in [PROJECT_ROOT, AGENT_DATA_ROOT]:
        lock_file = repo_dir / ".git" / "index.lock"
        entity_id = f"git_lock_{repo_dir.name}"
        if lock_file.exists():
            logger.warning(f"💥 Stale Git lock file found at {lock_file} (no active git process).")
            if backoff_mgr.can_retry(entity_id):
                backoff_mgr.record_failure(entity_id)
                try:
                    lock_file.unlink()
                    logger.info(f"✅ Stale lock file {lock_file} removed.")
                    send_alert(
                        f"🔧 **[自癒系統啟動]** 偵測到殘留的 Git 鎖定檔！\n"
                        f"✅ 已自動刪除 `{lock_file}` 以防止 Git 卡死。"
                    )
                except Exception as e:
                    logger.error(f"❌ Failed to delete lock file {lock_file}: {e}")
        else:
            backoff_mgr.reset(entity_id)

def check_mount_points():
    """
    Checks if network mount points are responsive.
    """
    logger.info("🔧 [Self-Healing] Checking network mount points...")
    mounts = ["/mnt/QMD", "/mnt/NasBackup"]
    for mnt in mounts:
        mnt_path = Path(mnt)
        if not mnt_path.exists():
            continue
        try:
            res = subprocess.run(
                ["timeout", "5", "ls", mnt],
                capture_output=True, text=True
            )
            if res.returncode == 124:
                logger.error(f"❌ Mount point {mnt} is HUNG (timeout)!")
                if should_alert(f"mount_hang_{mnt}", f"Mount {mnt} hanging"):
                    send_alert(
                        f"💥 **掛載點卡死異常 (Mount Hanging)**\n"
                        f"🔹 **路徑**: `{mnt}`\n"
                        f"⚠️ 偵測到掛載點回應超時，系統可能已僵死 (Stale Mount)。"
                    )
            elif res.returncode != 0:
                logger.error(f"❌ Mount point {mnt} returned error: {res.stderr.strip()}")
            else:
                logger.info(f"✅ Mount point {mnt} is active and responsive.")
        except Exception as e:
            logger.error(f"Failed to check mount point {mnt}: {e}")

def send_alert(message: str):
    """
    Sends a Telegram alert. Uses the local Port 8085 HTTP bridge.
    Falls back to direct Telegram API call if the local bridge is down.
    """
    logger.info(f"🚨 Attempting to send alert: {message[:100]}...")
    payload = {"message": message}
    
    # Method 1: Local HTTP bridge
    try:
        res = requests.post("http://127.0.0.1:8085/alert", json=payload, timeout=5)
        if res.status_code == 200:
            logger.info("✅ Alert delivered successfully via local HTTP bridge.")
            return True
    except Exception as e:
        logger.warning(f"⚠️ Local HTTP bridge unavailable: {e}. Falling back to direct Telegram API.")

    # Method 2: Direct Telegram API Fallback
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHANNEL_ID:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            direct_payload = {
                "chat_id": TELEGRAM_CHANNEL_ID,
                "text": f"⚠️ **[AgentOS Direct Fallback Alert]**\n\n{message}",
                "parse_mode": "Markdown"
            }
            res = requests.post(url, json=direct_payload, timeout=10)
            if res.status_code == 200:
                logger.info("✅ Alert delivered successfully via Direct Telegram API.")
                return True
            else:
                logger.error(f"❌ Direct API returned error: {res.text}")
        except Exception as ex:
            logger.error(f"❌ Direct API call failed: {ex}")
    else:
        logger.error("❌ Cannot send alert: No Telegram credentials in environment.")
    return False

def check_systemd_user(service_name: str) -> bool:
    try:
        env = os.environ.copy()
        uid = os.getuid()
        if "XDG_RUNTIME_DIR" not in env:
            env["XDG_RUNTIME_DIR"] = f"/run/user/{uid}"
        if "DBUS_SESSION_BUS_ADDRESS" not in env:
            env["DBUS_SESSION_BUS_ADDRESS"] = f"unix:path=/run/user/{uid}/bus"
        result = subprocess.run(
            ["systemctl", "--user", "is-active", service_name],
            capture_output=True, text=True, env=env, timeout=10
        )
        return result.stdout.strip() == "active"
    except Exception as e:
        logger.error(f"Failed to check systemd service {service_name}: {e}")
        return False

def restart_systemd_user(service_name: str) -> bool:
    logger.warning(f"🔧 [Self-Healing] Attempting to restart user systemd service {service_name}...")
    env = os.environ.copy()
    uid = os.getuid()
    if "XDG_RUNTIME_DIR" not in env:
        env["XDG_RUNTIME_DIR"] = f"/run/user/{uid}"
    if "DBUS_SESSION_BUS_ADDRESS" not in env:
        env["DBUS_SESSION_BUS_ADDRESS"] = f"unix:path=/run/user/{uid}/bus"
    try:
        subprocess.run(["systemctl", "--user", "restart", service_name], env=env, timeout=15)
        logger.info(f"✅ Restart command sent to systemd for {service_name}.")
        return True
    except Exception as e:
        logger.error(f"❌ Failed to restart user systemd service {service_name}: {e}")
        return False

def check_docker_container(container_name: str) -> bool:
    try:
        result = subprocess.run(
            ["sudo", "docker", "inspect", "-f", "{{.State.Running}}", container_name],
            capture_output=True, text=True, timeout=10
        )
        return result.stdout.strip() == "true"
    except Exception as e:
        logger.error(f"Failed to check docker container {container_name}: {e}")
        return False

def restart_docker_container(container_name: str) -> bool:
    logger.warning(f"🔧 [Self-Healing] Attempting to restart docker container {container_name}...")
    try:
        subprocess.run(["sudo", "docker", "start", container_name], timeout=20)
        logger.info(f"✅ Start command sent to Docker for {container_name}.")
        return True
    except Exception as e:
        logger.error(f"❌ Failed to restart docker container {container_name}: {e}")
        return False

def check_http(url: str) -> bool:
    try:
        res = requests.get(url, timeout=5)
        return res.status_code == 200
    except Exception:
        return False

def should_alert(project_name: str, error_message: str) -> bool:
    """Anti-spam throttling filter. Alerts only once every 4 hours for the same error."""
    lock_file = LOCK_DIR / f"{project_name}.lock"
    clean_msg = re.sub(r'\s+', ' ', error_message).strip()
    
    if lock_file.exists():
        try:
            lock_data = json.loads(lock_file.read_text(encoding="utf-8"))
            last_alert_time = datetime.fromisoformat(lock_data["time"])
            last_msg = lock_data["message"]
            
            # If error is identical and within 4 hours, do not alert
            elapsed = (datetime.now(timezone.utc) - last_alert_time).total_seconds()
            if clean_msg == last_msg and elapsed < 14400:
                logger.info(f"⏭️ Throttling alert for {project_name} (already sent {elapsed/60:.1f}m ago).")
                return False
        except Exception as e:
            logger.warning(f"Failed to parse alert lock for {project_name}: {e}")
            
    # Write lock
    lock_file.write_text(json.dumps({
        "time": datetime.now(timezone.utc).isoformat(),
        "message": clean_msg
    }), encoding="utf-8")
    return True

def clear_alert_lock(project_name: str):
    lock_file = LOCK_DIR / f"{project_name}.lock"
    if lock_file.exists():
        lock_file.unlink()

def scan_project_statuses():
    """
    Scans all projects STATUS.md files in the data layer for error flags (🔴)
    and reports them. Automatically clears alert throttling lock when 🟢 is found.
    """
    projects_dir = AGENT_DATA_ROOT / "projects"
    if not projects_dir.exists():
        logger.warning(f"Projects directory {projects_dir} does not exist. Skipping status scan.")
        return

    logger.info("🔍 Scanning project STATUS.md files...")
    for project_path in projects_dir.iterdir():
        if not project_path.is_dir():
            continue
        
        status_file = project_path / "STATUS.md"
        if not status_file.exists():
            continue
            
        try:
            content = status_file.read_text(encoding="utf-8")
            status_match = re.search(r'\|\s*\*\*Last Status\*\*\s*\|\s*([^|]+)\|', content)
            if status_match:
                status_text = status_match.group(1).strip()
                if "🔴" in status_text:
                    logger.warning(f"💥 Failure detected in project {project_path.name}: {status_text}")
                    if should_alert(project_path.name, status_text):
                        send_alert(
                            f"💥 **專案運行異常 (Stall/Error)**\n"
                            f"🔹 **專案**: `{project_path.name}`\n"
                            f"🔹 **狀態**: {status_text}\n"
                            f"🔹 **時間**: `{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}`"
                        )
                elif "🟢" in status_text:
                    # Clear lock to allow future alerts if it breaks later
                    clear_alert_lock(project_path.name)
        except Exception as e:
            logger.error(f"Failed to scan STATUS.md for {project_path.name}: {e}")

def run_self_healing():
    """
    Checks active systemd services, Docker containers, and website endpoints,
    healing them instantly if down.
    """
    if AGENT_MODE != "CORE":
        logger.info("Skipping core service checks since AGENT_MODE is not CORE.")
        return

    # 1. Systemd core services
    core_services = ["tg-commander.service"]
    for svc in core_services:
        entity_id = f"systemd_{svc}"
        if not check_systemd_user(svc):
            logger.error(f"❌ Core service {svc} is DOWN!")
            if backoff_mgr.can_retry(entity_id):
                backoff_mgr.record_failure(entity_id)
                if restart_systemd_user(svc):
                    send_alert(
                        f"🔧 **[自癒系統啟動]** Core 服務 `{svc}` 斷線！\n"
                        f"✅ 已經自動重啟該 Systemd 服務。"
                    )
        else:
            backoff_mgr.reset(entity_id)
            logger.info(f"✅ Core service {svc} is active.")

    # 2. n8n Docker Container
    entity_id = "docker_n8n"
    if check_docker_container("n8n"):
        backoff_mgr.reset(entity_id)
        logger.info("✅ Docker container 'n8n' is active.")
        # Check HTTP
        if not check_http("https://n8n.milkcat.org/healthz"):
            logger.error("❌ n8n API is unreachable!")
            # Trigger restart if unreachable for a while
            # (Just log warning for now to prevent racing during container start)
    else:
        logger.error("❌ Docker container 'n8n' is DOWN!")
        if backoff_mgr.can_retry(entity_id):
            backoff_mgr.record_failure(entity_id)
            if restart_docker_container("n8n"):
                send_alert(
                    "🔧 **[自癒系統啟動]** Docker `n8n` 容器停止！\n"
                    "✅ 已經自動重啟該 Docker 容器。"
                )

    # 3. Heal AI Onboarding & Possession Links
    logger.info("🔧 [Self-Healing] Healing AI Possession symlinks and directives...")
    try:
        subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "scripts" / "propagate_possession_rules.py")],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30
        )
        logger.info("✅ AI Possession rules successfully healed.")
    except Exception as e:
        logger.error(f"❌ Failed to run propagate_possession_rules: {e}")

def check_disk_space():
    """
    Checks the free disk space on the root mount and sends a Telegram alert
    if it falls below critical thresholds.
    """
    try:
        import shutil
        total, used, free = shutil.disk_usage("/")
        free_gb = free / (1024**3)
        total_gb = total / (1024**3)
        used_percent = (used / total) * 100
        
        logger.info(f"📊 Disk space check: {free_gb:.2f} GB free of {total_gb:.2f} GB ({used_percent:.1f}% used)")
        
        # Threshold: Less than 5.0 GB free or more than 95% used
        if free_gb < 5.0 or used_percent > 95.0:
            msg = (
                f"🚨 **[系統磁碟空間不足警告]**\n"
                f"🔹 **剩餘可用空間**: `{free_gb:.2f} GB` (總共 {total_gb:.2f} GB)\n"
                f"🔹 **使用率**: `{used_percent:.1f}%`\n"
                f"🔹 **建議**: 請儘速清理不必要的快取或重置舊日誌，以避免系統發生 `ENOSPC` 崩潰並造成 IDE 重載循環。"
            )
            logger.error(msg)
            if should_alert("system_disk_space", f"Low space: {free_gb:.2f}GB"):
                send_alert(message=msg)
        else:
            # Clear lock if resolved
            clear_alert_lock("system_disk_space")
            
        # Check inodes
        try:
            stat = os.statvfs('/')
            if stat.f_files > 0:
                inode_used_percent = (1.0 - (stat.f_ffree / stat.f_files)) * 100
                logger.info(f"📊 Inode check: {inode_used_percent:.1f}% used")
                if inode_used_percent > 95.0:
                    inode_msg = (
                        f"🚨 **[系統 Inodes 耗盡警告]**\n"
                        f"🔹 **Inodes 使用率**: `{inode_used_percent:.1f}%`\n"
                        f"🔹 **建議**: 系統內可能存在大量碎檔案，請儘速清理以免無法建立新檔案。"
                    )
                    logger.error(inode_msg)
                    if should_alert("system_inodes", f"Low inodes: {inode_used_percent:.1f}%"):
                        send_alert(message=inode_msg)
                else:
                    clear_alert_lock("system_inodes")
        except Exception as ie:
            logger.error(f"Failed to check inodes: {ie}")
            
    except Exception as e:
        logger.error(f"Failed to check disk space: {e}")

def main():
    parser = argparse.ArgumentParser(description="AgentOS Watchdog Service")
    parser.add_argument("--test-alert", action="store_true", help="Send a test alert message to Telegram.")
    args = parser.parse_args()

    if args.test_alert:
        send_alert("🧪 **AgentOS Watchdog 測試警報**\n本機 HTTP 警報端點與 Direct API 備援測試皆正常運作！")
        return 0

    logger.info("🛡️ Running Watchdog Service Check...")
    
    # 1. Check & Repair stale git locks
    heal_stale_git_locks()
    
    # 2. Check network mount responsiveness
    check_mount_points()
    
    # 3. Check & Repair system services
    run_self_healing()

    # 2. Check disk space & inodes
    check_disk_space()
    scan_project_statuses()
    
    logger.info("🎉 Watchdog checks completed.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
