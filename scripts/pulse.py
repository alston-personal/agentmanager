#!/usr/bin/env python3
import os
import json
import time
from pathlib import Path
from datetime import datetime, timezone

SHM_ROOT = Path("/dev/shm/leopardcat-swarm")
SHM_ROOT.mkdir(parents=True, exist_ok=True)

PULSE_FILE = SHM_ROOT / "pulse.json"
EVENTS_LOG = SHM_ROOT / "events.log"

def update_pulse(agent_name: str, task: str, status: str = "active"):
    """
    Updates the shared memory heartbeat board.
    Overwrites the current state for this specific agent.
    """
    pulse_data = {}
    if PULSE_FILE.exists():
        try:
            pulse_data = json.loads(PULSE_FILE.read_text())
        except (json.JSONDecodeError, ValueError):
            pulse_data = {}

    pulse_data[agent_name] = {
        "task": task,
        "status": status,
        "pid": os.getpid(),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

    with open(PULSE_FILE, "w") as f:
        json.dump(pulse_data, f, indent=2)

def log_event(agent_name: str, event_type: str, message: str, metadata: dict = None):
    """
    Broadcasts a real-time event through the LCS Bus.
    Append-only (jsonl format).
    """
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "agent": agent_name,
        "type": event_type,
        "message": message,
        "metadata": metadata or {}
    }
    with open(EVENTS_LOG, "a") as f:
        f.write(json.dumps(event) + "\n")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="LCS Pulse Utility")
    parser.add_argument("--agent", default="Gemini-IDE", help="Name of the agent")
    parser.add_argument("--task", help="Current task description")
    parser.add_argument("--status", default="active", help="Status (active/idle/error)")
    parser.add_argument("--event", help="Event type to broadcast")
    parser.add_argument("--message", help="Message to broadcast")

    args = parser.parse_args()

    if args.task:
        update_pulse(args.agent, args.task, args.status)
        print(f"✅ Pulsed: {args.agent} -> {args.task} ({args.status})")

    if args.event and args.message:
        log_event(args.agent, args.event, args.message)
        print(f"📣 Broadcasted Event: {args.event}: {args.message}")
