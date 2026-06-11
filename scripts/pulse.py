#!/usr/bin/env python3
"""
scripts/pulse.py — platform-aware heartbeat and event bus.

This is now a thin entrypoint over `agent_core.platform` so the caller does not
need to know whether the host is Linux, Windows, or macOS.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any

PROJECT_ROOT = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from agent_core.platform import get_platform_driver


def _driver(platform_name: str | None = None):
    return get_platform_driver(platform_name=platform_name)


def update_pulse(agent_name: str, task: str, status: str = "active", metadata: dict[str, Any] | None = None, platform_name: str | None = None) -> dict[str, Any]:
    return _driver(platform_name).write_pulse(agent_name, task, status, metadata=metadata or {})


def log_event(agent_name: str, event_type: str, message: str, metadata: dict[str, Any] | None = None, platform_name: str | None = None) -> dict[str, Any]:
    metadata = metadata or {}
    metadata.setdefault("agent", agent_name)
    return _driver(platform_name).append_event(event_type, message, metadata=metadata)


def restore_from_persistent(platform_name: str | None = None) -> dict[str, Any]:
    return _driver(platform_name).restore_pulse_board()


def main() -> int:
    parser = argparse.ArgumentParser(description="AgentOS pulse utility")
    parser.add_argument("--agent", default="Gemini-IDE", help="Name of the agent")
    parser.add_argument("--task", help="Current task description")
    parser.add_argument("--status", default="active", help="Status (active/idle/error)")
    parser.add_argument("--event", help="Event type to broadcast")
    parser.add_argument("--message", help="Message to broadcast")
    parser.add_argument("--metadata", default="{}", help="Optional JSON metadata for pulse/event writes")
    parser.add_argument("--platform", default=None, help="Override platform selection")
    parser.add_argument("--restore", action="store_true", help="Restore pulse from persistent store")
    parser.add_argument("--watch", action="store_true", help="Keep pulsing until the process is stopped")
    parser.add_argument("--interval", type=int, default=30, help="Watch interval in seconds")
    args = parser.parse_args()

    platform_driver = _driver(args.platform)

    try:
        metadata = json.loads(args.metadata) if args.metadata else {}
        if not isinstance(metadata, dict):
            metadata = {}
    except Exception:
        metadata = {}

    if args.restore:
        restored = platform_driver.restore_pulse_board()
        print(f"♻️  Restored {len(restored)} agents from persistent store")
        return 0

    if args.task:
        should_watch = args.watch or bool(os.environ.get("INVOCATION_ID"))
        lock = platform_driver.acquire_lock(f"pulse_{args.agent}")
        if should_watch:
            lock.acquire()
        try:
            while True:
                entry = platform_driver.write_pulse(args.agent, args.task, args.status, metadata=metadata)
                print(f"✅ Pulsed: {entry['agent']} → {entry['task']} ({entry['status']})")
                print(f"   Persistent backup: {platform_driver.persistent_state_dir() / 'pulse_snapshot.json'}")
                if not should_watch:
                    break
                time.sleep(max(args.interval, 5))
        finally:
            if should_watch:
                lock.release()

    if args.event and args.message:
        event = platform_driver.append_event(args.event, args.message, metadata={"agent": args.agent, **metadata})
        print(f"📣 Broadcasted Event: {event['event_type']}: {event['message']}")
        print(f"   Archive: {platform_driver.persistent_state_dir() / 'events_archive'}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
