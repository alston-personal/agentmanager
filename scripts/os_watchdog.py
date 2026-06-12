#!/usr/bin/env python3
"""
Antigravity AgentOS Self-Healing Watchdog (Event-Driven Async Version)
Actively monitors system services, Docker containers, and project STATUS.md files.
Automatically triggers self-healing routines and broadcasts Telegram alerts.
"""
import os
import sys
import re
import json
import logging
import asyncio
import argparse
from datetime import datetime, timezone
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Resolve dynamic paths
PROJECT_ROOT = Path(os.environ.get("AGENT_PROJECT_ROOT", Path(__file__).resolve().parents[1])).resolve()
AGENT_DATA_ROOT = Path(
    os.environ.get("AGENT_DATA_ROOT")
    or os.environ.get("AGENT_DATA_DIR")
    or Path.home() / "agent-data"
).expanduser()

LOCK_DIR = Path("/tmp/watchdog_locks")
LOCK_DIR.mkdir(parents=True, exist_ok=True)

# Setup logging
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

# Load Env
def load_env():
    # Use global.env or agentmanager.env via symlinks
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

# ---------------------------------------------------------
# Async Backoff Manager
# ---------------------------------------------------------
class AsyncBackoffManager:
    def __init__(self):
        self.state = {}
        self.lock = asyncio.Lock()

    async def can_retry(self, entity_id: str) -> bool:
        async with self.lock:
            if entity_id not in self.state:
                return True
            record = self.state[entity_id]
            failures = record.get("failures", 0)
            last_attempt = record.get("last_attempt")
            
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
                logger.info(f"⏳ [Backoff] {entity_id} in cooldown. {elapsed:.1f}/{delay} mins elapsed.")
                return False

    async def record_failure(self, entity_id: str):
        async with self.lock:
            record = self.state.get(entity_id, {"failures": 0})
            record["failures"] += 1
            record["last_attempt"] = datetime.now(timezone.utc)
            self.state[entity_id] = record
            logger.warning(f"📈 [Backoff] Recorded failure for {entity_id}. Total failures: {record['failures']}")

    async def reset(self, entity_id: str):
        async with self.lock:
            if entity_id in self.state:
                del self.state[entity_id]
                logger.info(f"🔄 [Backoff] Reset failure count for {entity_id}")

backoff_mgr = AsyncBackoffManager()

# ---------------------------------------------------------
# Async Alerting
# ---------------------------------------------------------
async def send_alert_async(message: str):
    logger.info(f"🚨 Attempting to send alert: {message[:100]}...")
    import aiohttp
    
    payload = {"message": message}
    try:
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post("http://127.0.0.1:8085/alert", json=payload, timeout=5) as res:
                    if res.status == 200:
                        logger.info("✅ Alert delivered successfully via local HTTP bridge.")
                        return True
            except Exception as e:
                logger.warning(f"⚠️ Local HTTP bridge unavailable: {e}. Falling back to direct API.")

            if TELEGRAM_BOT_TOKEN and TELEGRAM_CHANNEL_ID:
                url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
                direct_payload = {
                    "chat_id": TELEGRAM_CHANNEL_ID,
                    "text": f"⚠️ **[AgentOS Direct Fallback Alert]**\n\n{message}",
                    "parse_mode": "Markdown"
                }
                async with session.post(url, json=direct_payload, timeout=10) as res:
                    if res.status == 200:
                        logger.info("✅ Alert delivered successfully via Direct Telegram API.")
                        return True
                    else:
                        text = await res.text()
                        logger.error(f"❌ Direct API returned error: {text}")
            else:
                logger.error("❌ Cannot send alert: No Telegram credentials in environment.")
    except Exception as e:
        logger.error(f"❌ Failed to send alert: {e}")
    return False

def should_alert(project_name: str, error_message: str) -> bool:
    lock_file = LOCK_DIR / f"{project_name}.lock"
    clean_msg = re.sub(r'\s+', ' ', error_message).strip()
    
    if lock_file.exists():
        try:
            lock_data = json.loads(lock_file.read_text(encoding="utf-8"))
            last_alert_time = datetime.fromisoformat(lock_data["time"])
            last_msg = lock_data["message"]
            
            elapsed = (datetime.now(timezone.utc) - last_alert_time).total_seconds()
            if clean_msg == last_msg and elapsed < 14400:
                logger.info(f"⏭️ Throttling alert for {project_name} (already sent {elapsed/60:.1f}m ago).")
                return False
        except Exception as e:
            logger.warning(f"Failed to parse alert lock for {project_name}: {e}")
            
    lock_file.write_text(json.dumps({
        "time": datetime.now(timezone.utc).isoformat(),
        "message": clean_msg
    }), encoding="utf-8")
    return True

def clear_alert_lock(project_name: str):
    lock_file = LOCK_DIR / f"{project_name}.lock"
    if lock_file.exists():
        lock_file.unlink()

# ---------------------------------------------------------
# Event-Driven Status Monitoring
# ---------------------------------------------------------
class StatusEventHandler(FileSystemEventHandler):
    def __init__(self, loop):
        self.loop = loop

    def on_modified(self, event):
        if not event.is_directory and event.src_path.endswith("STATUS.md"):
            asyncio.run_coroutine_threadsafe(self.check_status_file(Path(event.src_path)), self.loop)

    async def check_status_file(self, status_file: Path):
        try:
            content = status_file.read_text(encoding="utf-8")
            status_match = re.search(r'\|\s*\*\*Last Status\*\*\s*\|\s*([^|]+)\|', content)
            if status_match:
                status_text = status_match.group(1).strip()
                project_name = status_file.parent.name
                if "🔴" in status_text:
                    logger.warning(f"💥 Failure detected in project {project_name}: {status_text}")
                    if should_alert(project_name, status_text):
                        await send_alert_async(
                            f"💥 **專案運行異常 (Stall/Error)**\n"
                            f"🔹 **專案**: `{project_name}`\n"
                            f"🔹 **狀態**: {status_text}\n"
                            f"🔹 **時間**: `{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}`"
                        )
                elif "🟢" in status_text:
                    clear_alert_lock(project_name)
        except Exception as e:
            logger.error(f"Failed to scan STATUS.md for {status_file}: {e}")

# ---------------------------------------------------------
# Async Health Checks
# ---------------------------------------------------------
async def check_systemd_user(service_name: str) -> bool:
    env = os.environ.copy()
    uid = os.getuid()
    if "XDG_RUNTIME_DIR" not in env:
        env["XDG_RUNTIME_DIR"] = f"/run/user/{uid}"
    if "DBUS_SESSION_BUS_ADDRESS" not in env:
        env["DBUS_SESSION_BUS_ADDRESS"] = f"unix:path=/run/user/{uid}/bus"
    
    proc = await asyncio.create_subprocess_exec(
        "systemctl", "--user", "is-active", service_name,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env
    )
    stdout, _ = await proc.communicate()
    return stdout.decode().strip() == "active"

async def restart_systemd_user(service_name: str) -> bool:
    env = os.environ.copy()
    uid = os.getuid()
    if "XDG_RUNTIME_DIR" not in env:
        env["XDG_RUNTIME_DIR"] = f"/run/user/{uid}"
    if "DBUS_SESSION_BUS_ADDRESS" not in env:
        env["DBUS_SESSION_BUS_ADDRESS"] = f"unix:path=/run/user/{uid}/bus"
    
    proc = await asyncio.create_subprocess_exec(
        "systemctl", "--user", "restart", service_name,
        env=env
    )
    await proc.wait()
    return proc.returncode == 0

async def check_docker_container(container_name: str) -> bool:
    proc = await asyncio.create_subprocess_exec(
        "sudo", "docker", "inspect", "-f", "{{.State.Running}}", container_name,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, _ = await proc.communicate()
    return stdout.decode().strip() == "true"

async def restart_docker_container(container_name: str) -> bool:
    proc = await asyncio.create_subprocess_exec(
        "sudo", "docker", "start", container_name
    )
    await proc.wait()
    return proc.returncode == 0

async def heal_core_services():
    if AGENT_MODE != "CORE":
        return

    core_services = ["tg-commander.service", "os-lobster.service"]
    for svc in core_services:
        entity_id = f"systemd_{svc}"
        if not await check_systemd_user(svc):
            logger.error(f"❌ Core service {svc} is DOWN!")
            if await backoff_mgr.can_retry(entity_id):
                await backoff_mgr.record_failure(entity_id)
                if await restart_systemd_user(svc):
                    await send_alert_async(
                        f"🔧 **[自癒系統啟動]** Core 服務 `{svc}` 斷線！\n"
                        f"✅ 已經自動重啟該 Systemd 服務。"
                    )
        else:
            await backoff_mgr.reset(entity_id)
            
    # Docker
    entity_id = "docker_n8n"
    if await check_docker_container("n8n"):
        await backoff_mgr.reset(entity_id)
    else:
        logger.error("❌ Docker container 'n8n' is DOWN!")
        if await backoff_mgr.can_retry(entity_id):
            await backoff_mgr.record_failure(entity_id)
            if await restart_docker_container("n8n"):
                await send_alert_async(
                    "🔧 **[自癒系統啟動]** Docker `n8n` 容器停止！\n"
                    "✅ 已經自動重啟該 Docker 容器。"
                )

async def check_mount_points():
    mounts = ["/mnt/QMD", "/mnt/NasBackup"]
    for mnt in mounts:
        mnt_path = Path(mnt)
        if not mnt_path.exists():
            continue
        try:
            proc = await asyncio.create_subprocess_exec(
                "timeout", "5", "ls", mnt,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await proc.wait()
            if proc.returncode == 124:
                logger.error(f"❌ Mount point {mnt} is HUNG (timeout)!")
                if should_alert(f"mount_hang_{mnt}", f"Mount {mnt} hanging"):
                    await send_alert_async(
                        f"💥 **掛載點卡死異常 (Mount Hanging)**\n"
                        f"🔹 **路徑**: `{mnt}`\n"
                        f"⚠️ 偵測到掛載點回應超時，系統可能已僵死。"
                    )
        except Exception as e:
            logger.error(f"Failed to check mount point {mnt}: {e}")

async def check_disk_space():
    try:
        import shutil
        total, used, free = shutil.disk_usage("/")
        free_gb = free / (1024**3)
        total_gb = total / (1024**3)
        used_percent = (used / total) * 100
        
        if free_gb < 5.0 or used_percent > 95.0:
            msg = (
                f"🚨 **[系統磁碟空間不足警告]**\n"
                f"🔹 **剩餘可用空間**: `{free_gb:.2f} GB` (總共 {total_gb:.2f} GB)\n"
                f"🔹 **使用率**: `{used_percent:.1f}%`\n"
                f"🔹 **建議**: 請儘速清理不必要的快取或重置舊日誌，以避免系統發生 `ENOSPC` 崩潰並造成 IDE 重載循環。"
            )
            logger.error(msg)
            if should_alert("system_disk_space", f"Low space: {free_gb:.2f}GB"):
                await send_alert_async(message=msg)
        else:
            clear_alert_lock("system_disk_space")
            
        try:
            stat = os.statvfs('/')
            if stat.f_files > 0:
                inode_used_percent = (1.0 - (stat.f_ffree / stat.f_files)) * 100
                if inode_used_percent > 95.0:
                    inode_msg = (
                        f"🚨 **[系統 Inodes 耗盡警告]**\n"
                        f"🔹 **Inodes 使用率**: `{inode_used_percent:.1f}%`\n"
                        f"🔹 **建議**: 系統內可能存在大量碎檔案，請儘速清理以免無法建立新檔案。"
                    )
                    logger.error(inode_msg)
                    if should_alert("system_inodes", f"Low inodes: {inode_used_percent:.1f}%"):
                        await send_alert_async(message=inode_msg)
                else:
                    clear_alert_lock("system_inodes")
        except Exception as ie:
            logger.error(f"Failed to check inodes: {ie}")
    except Exception as e:
        logger.error(f"Failed to check disk space: {e}")

async def heal_stale_git_locks():
    try:
        proc = await asyncio.create_subprocess_exec("pgrep", "-x", "git")
        await proc.wait()
        git_running = (proc.returncode == 0)
    except Exception:
        git_running = False

    if git_running:
        return

    for repo_dir in [PROJECT_ROOT, AGENT_DATA_ROOT]:
        lock_file = repo_dir / ".git" / "index.lock"
        entity_id = f"git_lock_{repo_dir.name}"
        if lock_file.exists():
            logger.warning(f"💥 Stale Git lock file found at {lock_file}")
            if await backoff_mgr.can_retry(entity_id):
                await backoff_mgr.record_failure(entity_id)
                try:
                    lock_file.unlink()
                    logger.info(f"✅ Stale lock file {lock_file} removed.")
                    await send_alert_async(
                        f"🔧 **[自癒系統啟動]** 偵測到殘留的 Git 鎖定檔！\n"
                        f"✅ 已自動刪除 `{lock_file}` 以防止 Git 卡死。"
                    )
                except Exception as e:
                    logger.error(f"❌ Failed to delete lock file {lock_file}: {e}")
        else:
            await backoff_mgr.reset(entity_id)

async def background_health_loop():
    while True:
        try:
            await heal_stale_git_locks()
            await check_mount_points()
            await check_disk_space()
            await heal_core_services()
        except Exception as e:
            logger.error(f"Error in background_health_loop: {e}")
        await asyncio.sleep(300) # Every 5 minutes

async def main():
    parser = argparse.ArgumentParser(description="AgentOS Watchdog Service")
    parser.add_argument("--test-alert", action="store_true", help="Send a test alert message to Telegram.")
    args = parser.parse_args()

    if args.test_alert:
        await send_alert_async("🧪 **AgentOS Watchdog 測試警報**\n本機 HTTP 警報端點與 Direct API 備援測試皆正常運作！")
        return

    logger.info("🛡️ Starting AgentOS Watchdog Event-Driven Daemon...")
    
    loop = asyncio.get_running_loop()
    observer = Observer()
    handler = StatusEventHandler(loop)
    
    projects_dir = AGENT_DATA_ROOT / "projects"
    if projects_dir.exists():
        observer.schedule(handler, str(projects_dir), recursive=True)
        observer.start()
        logger.info(f"👀 Observing STATUS.md changes in {projects_dir}")
    else:
        logger.warning(f"Projects directory {projects_dir} does not exist.")

    # Trigger an initial check of all statuses
    for project_path in projects_dir.iterdir():
        if project_path.is_dir():
            status_file = project_path / "STATUS.md"
            if status_file.exists():
                asyncio.run_coroutine_threadsafe(handler.check_status_file(status_file), loop)

    # Run background health tasks concurrently
    health_task = asyncio.create_task(background_health_loop())
    
    try:
        await asyncio.gather(health_task)
    except KeyboardInterrupt:
        logger.info("Shutting down Watchdog...")
    except asyncio.CancelledError:
        pass
    finally:
        if observer.is_alive():
            observer.stop()
            observer.join()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
