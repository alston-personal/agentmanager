#!/usr/bin/env python3
"""Issue a least-privilege ONE client token for the account-scoped ChatGPT node."""

from __future__ import annotations

import argparse
import json
import os

from agent_core.client_auth import ClientTokenStore
from agent_core.distributed_control_plane import DistributedControlPlane


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=os.environ.get("AGENTOS_CONTROL_PLANE_DB"))
    parser.add_argument("--principal-id", required=True)
    parser.add_argument("--project", action="append", dest="projects")
    parser.add_argument("--ttl-days", type=int, default=90)
    args = parser.parse_args()

    if not args.db:
        raise SystemExit("--db or AGENTOS_CONTROL_PLANE_DB is required")
    projects = tuple(args.projects or ["*"])
    store = DistributedControlPlane(args.db)
    issued = ClientTokenStore(store).issue(
        f"chatgpt:{args.principal_id}",
        label="ChatGPT Cloud Node",
        permissions=("project.read", "task.read"),
        projects=projects,
        capabilities=("*",),
        ttl_days=args.ttl_days,
    )
    print(json.dumps(issued, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
