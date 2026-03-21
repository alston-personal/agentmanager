"""
agent_memory/process_registry.py
Process identity and registry for Agent OS.

Addresses the "process 化" critique: agents need formal identity,
not just a PID in a volatile JSON file.

Architecture:
- Each agent invocation has a unique agent_id + session_id
- Process registry persists to agent-data/runtime/processes.json (durable)
- Also syncs to /dev/shm/leopardcat-swarm/pulse.json (fast, for swarm monitor)
- On shutdown, agents mark themselves as idle
- Watchdog can detect stale processes (last_seen > threshold)

This enables:
- spawn tree tracking (parent_agent_id)
- channel-aware routing (ide | telegram | cli | api)
- swarm coordination without IDE attachment
"""
from __future__ import annotations

import json
import os
import signal
import atexit
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from agent_core.config import (
    AGENT_DATA_ROOT,
    LCS_SHM_ROOT,
    LCS_PULSE_FILE,
)

# Persistent process registry (survives reboot)
RUNTIME_DIR = AGENT_DATA_ROOT / "runtime"
PROCESS_REGISTRY_FILE = RUNTIME_DIR / "processes.json"


def register_process(
    agent_id: str,
    channel: str = "ide",
    task: str = "starting",
    parent_agent_id: Optional[str] = None,
    session_id: Optional[str] = None,
) -> dict:
    """
    Register this agent process in both:
    - Persistent: agent-data/runtime/processes.json
    - Volatile: /dev/shm/leopardcat-swarm/pulse.json

    Returns the process entry dict.
    """
    now = datetime.now(timezone.utc).isoformat()
    entry = {
        "agent_id": agent_id,
        "pid": os.getpid(),
        "channel": channel,
        "task": task,
        "status": "active",
        "started_at": now,
        "last_seen": now,
        "session_id": session_id,
        "parent_agent_id": parent_agent_id,
    }

    _write_persistent(agent_id, entry)
    _write_volatile(agent_id, entry)

    # Auto-deregister on clean exit
    atexit.register(deregister_process, agent_id)

    return entry


def heartbeat(agent_id: str, task: str = None, status: str = "active") -> None:
    """
    Update the last_seen timestamp and optionally the current task.
    Call periodically from long-running agents.
    """
    now = datetime.now(timezone.utc).isoformat()

    # Update persistent
    registry = _load_persistent()
    if agent_id in registry.get("agents", {}):
        registry["agents"][agent_id]["last_seen"] = now
        registry["agents"][agent_id]["status"] = status
        if task:
            registry["agents"][agent_id]["task"] = task
        _save_persistent(registry)

    # Update volatile LCS
    try:
        pulse = _load_volatile()
        if agent_id in pulse:
            pulse[agent_id]["timestamp"] = now
            pulse[agent_id]["status"] = status
            if task:
                pulse[agent_id]["task"] = task
        _save_volatile(pulse)
    except Exception:
        pass


def deregister_process(agent_id: str) -> None:
    """Mark an agent as idle on exit."""
    now = datetime.now(timezone.utc).isoformat()

    registry = _load_persistent()
    if agent_id in registry.get("agents", {}):
        registry["agents"][agent_id]["status"] = "idle"
        registry["agents"][agent_id]["last_seen"] = now
        _save_persistent(registry)

    try:
        pulse = _load_volatile()
        if agent_id in pulse:
            pulse[agent_id]["status"] = "idle"
            pulse[agent_id]["timestamp"] = now
        _save_volatile(pulse)
    except Exception:
        pass


def list_active_processes() -> list[dict]:
    """Return all currently active agent processes from persistent registry."""
    registry = _load_persistent()
    return [
        entry for entry in registry.get("agents", {}).values()
        if entry.get("status") == "active"
    ]


def get_process(agent_id: str) -> Optional[dict]:
    """Look up a specific agent's process entry."""
    registry = _load_persistent()
    return registry.get("agents", {}).get(agent_id)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load_persistent() -> dict:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    if not PROCESS_REGISTRY_FILE.exists():
        return {"agents": {}, "updated_at": ""}
    try:
        return json.loads(PROCESS_REGISTRY_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"agents": {}, "updated_at": ""}


def _save_persistent(data: dict) -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    PROCESS_REGISTRY_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _write_persistent(agent_id: str, entry: dict) -> None:
    registry = _load_persistent()
    registry.setdefault("agents", {})[agent_id] = entry
    _save_persistent(registry)


def _load_volatile() -> dict:
    if not LCS_PULSE_FILE.exists():
        return {}
    try:
        return json.loads(LCS_PULSE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_volatile(data: dict) -> None:
    try:
        LCS_SHM_ROOT.mkdir(parents=True, exist_ok=True)
        LCS_PULSE_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:
        pass


def _write_volatile(agent_id: str, entry: dict) -> None:
    pulse = _load_volatile()
    # LCS pulse format (compatible with swarm_top.py)
    pulse[agent_id] = {
        "task": entry["task"],
        "status": entry["status"],
        "pid": entry["pid"],
        "timestamp": entry["started_at"],
        "channel": entry["channel"],
        "session_id": entry.get("session_id", ""),
    }
    _save_volatile(pulse)
