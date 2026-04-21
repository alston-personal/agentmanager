#!/usr/bin/env python3
"""
scripts/pulse.py — LCS Pulse Utility (upgraded)

Dual-write architecture:
  VOLATILE  : /dev/shm/leopardcat-swarm/pulse.json   (fast, for swarm_top.py live monitor)
  PERSISTENT: agent-data/runtime/pulse_snapshot.json (survives reboot, for cold-start recovery)

Both are always updated together. On startup, if volatile is empty but persistent exists,
agents can restore from persistent.

Usage (CLI):
    python3 scripts/pulse.py --agent Gemini-IDE --task "Working on X" --status active
    python3 scripts/pulse.py --agent Gemini-IDE --event workflow_started --message "/report started"
"""
import os
import json
import sys
import time
from pathlib import Path
from datetime import datetime, timezone

# Add project root to path to import service_utils
PROJECT_ROOT_DETECTED = Path(__file__).resolve().parent.parent
sys.path.append(str(PROJECT_ROOT_DETECTED))
from scripts.service_utils import setup_locking, handle_signals

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SHM_ROOT = Path("/dev/shm/leopardcat-swarm")
SHM_ROOT.mkdir(parents=True, exist_ok=True)

PULSE_FILE = SHM_ROOT / "pulse.json"
EVENTS_LOG = SHM_ROOT / "events.log"

# Add project root to sys.path to import agent_core
PROJECT_ROOT_DETECTED = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT_DETECTED) not in sys.path:
    sys.path.append(str(PROJECT_ROOT_DETECTED))

from agent_core import config
_AGENT_DATA_ROOT = config.AGENT_DATA_ROOT
_RUNTIME_DIR = config.RUNTIME_DIR
PERSISTENT_PULSE = _RUNTIME_DIR / "pulse_snapshot.json"
PERSISTENT_EVENTS_ARCHIVE_DIR = _RUNTIME_DIR / "events_archive"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def update_pulse(agent_name: str, task: str, status: str = "active") -> None:
    """
    Update this agent's heartbeat entry in both volatile and persistent stores.
    """
    pulse_data = _read_volatile_pulse()
    pulse_data[agent_name] = {
        "task": task,
        "status": status,
        "pid": os.getpid(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    _write_volatile_pulse(pulse_data)
    _write_persistent_pulse(pulse_data)  # NEW: persist to agent-data


def log_event(agent_name: str, event_type: str, message: str, metadata: dict = None) -> None:
    """
    Broadcast a real-time event through the LCS Bus (append-only JSONL).
    Also writes to agent-data/runtime/events_archive/YYYY-MM-DD.jsonl for durability.
    """
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "agent": agent_name,
        "type": event_type,
        "message": message,
        "metadata": metadata or {},
    }
    line = json.dumps(event) + "\n"

    # Volatile write
    with open(EVENTS_LOG, "a") as f:
        f.write(line)

    # Persistent write (NEW)
    _write_persistent_event(line)


def restore_from_persistent() -> dict:
    """
    Cold-start recovery: load last known pulse state from persistent store.
    Call this at agent startup if /dev/shm is empty.
    """
    if not PERSISTENT_PULSE.exists():
        return {}
    try:
        data = json.loads(PERSISTENT_PULSE.read_text())
        # Mark all restored entries as idle (they were from a previous process)
        for entry in data.values():
            entry["status"] = "idle (restored)"
        _write_volatile_pulse(data)
        return data
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _read_volatile_pulse() -> dict:
    if PULSE_FILE.exists():
        try:
            return json.loads(PULSE_FILE.read_text())
        except Exception:
            pass
    # Cold-start: try to restore from persistent
    if not PULSE_FILE.exists() and PERSISTENT_PULSE.exists():
        return restore_from_persistent()
    return {}


def _write_volatile_pulse(data: dict) -> None:
    with open(PULSE_FILE, "w") as f:
        json.dump(data, f, indent=2)


def _write_persistent_pulse(data: dict) -> None:
    try:
        _RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        PERSISTENT_PULSE.write_text(json.dumps(data, indent=2))
    except Exception:
        pass  # Never crash the caller over persistence failure


def _write_persistent_event(line: str) -> None:
    try:
        PERSISTENT_EVENTS_ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        archive_file = PERSISTENT_EVENTS_ARCHIVE_DIR / f"{today}.jsonl"
        with open(archive_file, "a") as f:
            f.write(line)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="LCS Pulse Utility")
    parser.add_argument("--agent", default="Gemini-IDE", help="Name of the agent")
    parser.add_argument("--task", help="Current task description")
    parser.add_argument("--status", default="active", help="Status (active/idle/error)")
    parser.add_argument("--event", help="Event type to broadcast")
    parser.add_argument("--message", help="Message to broadcast")
    parser.add_argument("--restore", action="store_true", help="Restore pulse from persistent store")
    parser.add_argument("--watch", action="store_true", help="Keep pulsing until the process is stopped")
    parser.add_argument("--interval", type=int, default=30, help="Watch interval in seconds")

    args = parser.parse_args()

    if args.restore:
        restored = restore_from_persistent()
        print(f"♻️  Restored {len(restored)} agents from persistent store")
        sys.exit(0)

    if args.task:
        should_watch = args.watch or bool(os.environ.get("INVOCATION_ID"))
        if should_watch:
            # 確保只有一個實例在運行 (Lock & Replace)
            # 使用 agent name 做為 lock 的一部分，允許多個 agent 同時 pulse
            _lock = setup_locking(f"pulse_{args.agent}", replace=True)
            handle_signals()

        while True:
            update_pulse(args.agent, args.task, args.status)
            print(f"✅ Pulsed: {args.agent} → {args.task} ({args.status})")
            print(f"   Persistent backup: {PERSISTENT_PULSE}")
            if not should_watch:
                break
            time.sleep(max(args.interval, 5))

    if args.event and args.message:
        log_event(args.agent, args.event, args.message)
        print(f"📣 Broadcasted Event: {args.event}: {args.message}")
        print(f"   Archive: {PERSISTENT_EVENTS_ARCHIVE_DIR}")
