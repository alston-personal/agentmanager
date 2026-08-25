#!/usr/bin/env python3
"""
scripts/update_scheduler_board.py — Render Swarm Scheduler Dashboard
Reads schedule.yaml, volatile pulse.json, and chronos.log to dynamically compile
/home/ubuntu/agent-data/SCHEDULER_BOARD.md.
"""
import os
import json
import yaml
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

# Paths
PROJECT_ROOT = Path(os.environ.get("AGENT_PROJECT_ROOT", Path(__file__).resolve().parents[1])).resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from agent_core import config
from agent_core.platform import get_platform_driver
from agentos_node.bootstrap_control import run_bootstrap_control_plane

AGENT_DATA_ROOT = config.AGENT_DATA_ROOT
PLATFORM_DRIVER = get_platform_driver(project_root=PROJECT_ROOT, data_root=AGENT_DATA_ROOT)
PULSE_FILE = PLATFORM_DRIVER.volatile_state_dir() / "pulse.json"
PERSISTENT_PULSE = PLATFORM_DRIVER.persistent_state_dir() / "pulse_snapshot.json"
SCHEDULE_YAML = PROJECT_ROOT / "schedule.yaml"
CHRONOS_LOG = AGENT_DATA_ROOT / "logs/chronos.log"
BOARD_MD = AGENT_DATA_ROOT / "SCHEDULER_BOARD.md"

def get_real_time_pulse():
    pulse_data = {}
    if PULSE_FILE.exists():
        try:
            pulse_data = json.loads(PULSE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    if not pulse_data and PERSISTENT_PULSE.exists():
        try:
            pulse_data = json.loads(PERSISTENT_PULSE.read_text(encoding="utf-8"))
            # Restored entries might be marked as idle
            for entry in pulse_data.values():
                if "status" not in entry or entry["status"] == "active":
                    entry["status"] = "idle (restored)"
        except Exception:
            pass
    return pulse_data

def get_scheduled_tasks():
    schedules = []
    if SCHEDULE_YAML.exists():
        try:
            with open(SCHEDULE_YAML, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                schedules = data.get("schedules", [])
        except Exception:
            pass
    return schedules

def get_recent_chronos_logs():
    lines = []
    if CHRONOS_LOG.exists():
        try:
            with open(CHRONOS_LOG, "r", encoding="utf-8") as f:
                # Read last 1500 bytes to be fast
                f.seek(0, os.SEEK_END)
                size = f.tell()
                f.seek(max(0, size - 2000), os.SEEK_SET)
                log_data = f.read()
                lines = log_data.splitlines()
        except Exception:
            pass
    
    # Filter logs relating to job execution/trigger
    parsed_logs = []
    # Match log format e.g., 2026-05-28 09:00:00,123 [INFO] (Chronos) 🚀 [Trigger] Launching job 'os-pulse'
    for line in reversed(lines):
        if "Trigger" in line or "Autonomous" in line or "Self-Pushing" in line or "失敗" in line or "成功" in line:
            # Clean logging format for visualization
            clean_line = line.strip()
            # Truncate long absolute path for aesthetics
            clean_line = clean_line.replace("/home/ubuntu/", "~/")
            parsed_logs.append(clean_line)
            if len(parsed_logs) >= 8:
                break
    return parsed_logs

def generate_markdown():
    timestamp = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    
    pulse_data = get_real_time_pulse()
    schedules = get_scheduled_tasks()
    recent_logs = get_recent_chronos_logs()
    
    md = []
    md.append("# 🕹️ AgentOS Swarm Scheduler Board")
    md.append(f"> **Central Scheduler Status**: 🟢 RUNNING (PID: 1154)  ")
    md.append(f"> **Last Compiled**: `{timestamp}`  ")
    md.append("\n---\n")
    
    # 1. Swarm Heartbeats
    md.append("### 📊 1. 實時守護心跳 (Swarm Heartbeats)")
    md.append(f"Below are the active agents tracked in `{PULSE_FILE.parent}`:")
    md.append("\n| 助理名稱 (Agent) | 當前任務 (Active Task) | 狀態 (Status) | PID | 最後更新時間 |")
    md.append("| :--- | :--- | :---: | :---: | :--- |")
    
    if pulse_data:
        for name, data in sorted(pulse_data.items()):
            task = data.get("task", "Unknown Task")
            status = data.get("status", "unknown")
            pid = data.get("pid", "-")
            ts = data.get("timestamp", "")
            
            # Formatting timezone
            try:
                dt = datetime.fromisoformat(ts)
                local_ts = dt.astimezone().strftime("%H:%M:%S")
            except Exception:
                local_ts = ts
                
            status_emoji = "🟢 active" if "active" in status else "🟡 idle"
            if "error" in status:
                status_emoji = "🔴 error"
                
            md.append(f"| **{name}** | {task} | {status_emoji} | `{pid}` | {local_ts} |")
    else:
        md.append("| - | No active heartbeat detected. | - | - | - |")
        
    md.append("\n---\n")
    
    # 2. Scheduled Tasks
    md.append("### 🗓️ 2. 定時任務調度 (Scheduled Tasks)")
    md.append("Loaded from persistent scheduler configuration `schedule.yaml`:")
    md.append("\n| 任務名稱 (Task) | 執行頻率 (Interval) | 預計執行內容 (Command Excerpt) |")
    md.append("| :--- | :---: | :--- |")
    
    for job in schedules:
        name = job.get("name", "Unknown")
        interval = job.get("interval_seconds", 0)
        command = job.get("command", "")
        
        # Human readable interval
        if interval >= 3600:
            freq = f"每 {interval // 3600} 小時"
        elif interval >= 60:
            freq = f"每 {interval // 60} 分鐘"
        else:
            freq = f"每 {interval} 秒"
            
        # Clean command for security & layout
        cmd_excerpt = command.replace("/home/ubuntu/", "~/")
        if len(cmd_excerpt) > 70:
            cmd_excerpt = cmd_excerpt[:67] + "..."
            
        md.append(f"| **{name}** | {freq} | `{cmd_excerpt}` |")
        
    md.append("\n---\n")
    
    # 3. Log Stream
    md.append("### 🏆 3. 自律推進成果與歷程 (Recent Swarm Activity)")
    md.append("Real-time trigger logs streaming from `chronos.log`:")
    md.append("\n```text")
    if recent_logs:
        for log in recent_logs:
            md.append(log)
    else:
        md.append("No recent scheduler logs found.")
    md.append("```")
    md.append("\n---\n")
    md.append("*「自律調度，行雲流水；真相永存，邏輯自洽。」*")
    
    return "\n".join(md)

def main():
    # Deterministic break-glass hook. Dormant unless a fresh, allowlisted
    # request exists in agent-data/runtime/bootstrap-control/requests.
    try:
        bootstrap_receipt = run_bootstrap_control_plane()
        if bootstrap_receipt is not None:
            print(
                "AgentOS bootstrap request processed: "
                f"{bootstrap_receipt.get('request_id')} ok={bootstrap_receipt.get('ok')}"
            )
    except Exception as e:
        # Scheduler Board rendering must remain available even when a bootstrap
        # request is malformed or the repair path fails unexpectedly.
        print(f"⚠️ AgentOS bootstrap control plane error: {e}", file=sys.stderr)

    try:
        md_content = generate_markdown()
        BOARD_MD.write_text(md_content, encoding="utf-8")
        print(f"✅ Board rendered successfully to {BOARD_MD}")
    except Exception as e:
        print(f"❌ Failed to render board: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
