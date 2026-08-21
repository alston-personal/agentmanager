#!/usr/bin/env python3
"""Run the Distributed AgentOS Control Plane HTTP gateway."""

from __future__ import annotations

import argparse
import os

from agent_core.distributed_control_plane import DistributedControlPlane
from agent_core.distributed_gateway import DistributedGatewayServer, DistributedGatewayService


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=os.getenv("AGENTOS_CONTROL_PLANE_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("AGENTOS_CONTROL_PLANE_PORT", "8765")))
    parser.add_argument("--db", default=os.getenv("AGENTOS_CONTROL_PLANE_DB"))
    args = parser.parse_args()

    token = os.getenv("AGENTOS_CONTROL_PLANE_TOKEN")
    store = DistributedControlPlane(args.db) if args.db else DistributedControlPlane()
    service = DistributedGatewayService(store)
    server = DistributedGatewayServer((args.host, args.port), service, token=token)
    print(f"Distributed AgentOS gateway listening on http://{args.host}:{args.port}")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
