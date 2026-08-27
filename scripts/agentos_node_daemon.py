#!/usr/bin/env python3
"""Persistent pull-node daemon for AgentOS Core v0.1."""

from __future__ import annotations

import os
import signal
import time

from agentos_node.control_plane_client import ControlPlaneClient
from agentos_node.remote_worker import build_default_worker, run_once


STOP = False


def _stop(*_: object) -> None:
    global STOP
    STOP = True


def main() -> int:
    gateway = os.getenv("AGENTOS_CONTROL_PLANE_URL", "http://127.0.0.1:8765")
    runtime_id = os.getenv("AGENTOS_RUNTIME_ID", "oracle-core-node")
    token = os.getenv("AGENTOS_CONTROL_PLANE_TOKEN")
    poll_seconds = max(float(os.getenv("AGENTOS_NODE_POLL_SECONDS", "1")), 0.2)
    client = ControlPlaneClient(gateway, token=token, allow_insecure_http=True)
    worker = build_default_worker(runtime_id)

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    while not STOP:
        try:
            outcome = run_once(client, runtime_id, worker=worker, lease_seconds=60)
            if outcome.get("status") == "idle":
                time.sleep(poll_seconds)
        except Exception as exc:
            print(f"agentos-node-daemon error: {exc}", flush=True)
            time.sleep(min(poll_seconds * 5, 10))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
