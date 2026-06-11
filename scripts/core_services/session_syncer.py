#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent_core.platform import get_platform_driver


def main() -> int:
    platform_name = os.environ.get("AGENT_PLATFORM")
    driver = get_platform_driver(platform_name=platform_name)
    interval = int(os.environ.get("SESSION_SYNC_INTERVAL", "60"))

    lock = driver.acquire_lock("session_syncer")
    lock.acquire()
    try:
        print(f"🐾 Session Syncer started on {driver.platform_name()} (PID: {os.getpid()})")
        while True:
            result = driver.sync_transcripts()
            if result.get("copied"):
                print(f"✅ Synced {result['copied']} transcript files -> {result['destination']}")
            time.sleep(max(interval, 5))
    finally:
        lock.release()


if __name__ == "__main__":
    raise SystemExit(main())
