#!/usr/bin/env python3
"""Lease and execute one Distributed AgentOS task through the HTTP gateway."""

from __future__ import annotations

import argparse
import json
import os

from agentos_node.control_plane_client import ControlPlaneClient
from agentos_node.remote_worker import run_once


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gateway", default=os.getenv("AGENTOS_CONTROL_PLANE_URL"))
    parser.add_argument("--runtime-id", default=os.getenv("AGENTOS_RUNTIME_ID"))
    parser.add_argument("--lease-seconds", type=int, default=60)
    parser.add_argument("--allow-insecure-http", action="store_true")
    args = parser.parse_args()

    if not args.gateway:
        parser.error("--gateway or AGENTOS_CONTROL_PLANE_URL is required")
    if not args.runtime_id:
        parser.error("--runtime-id or AGENTOS_RUNTIME_ID is required")

    client = ControlPlaneClient(
        args.gateway,
        token=os.getenv("AGENTOS_CONTROL_PLANE_TOKEN"),
        allow_insecure_http=args.allow_insecure_http,
    )
    outcome = run_once(client, args.runtime_id, lease_seconds=args.lease_seconds)
    print(json.dumps(outcome, ensure_ascii=False, sort_keys=True))
    return 0 if outcome["status"] in {"idle", "succeeded"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
