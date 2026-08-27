#!/usr/bin/env python3
"""Run the localhost ChatGPT AgentOS continuation companion."""

from __future__ import annotations

import argparse
import os

from agentos_node.chatgpt_local_companion import (
    ChatGPTLocalCompanionServer,
    ChatGPTLocalCompanionService,
)
from agentos_node.control_plane_client import ControlPlaneClient


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=int(os.environ.get("AGENTOS_CHATGPT_COMPANION_PORT", "8766")))
    parser.add_argument("--runtime-id", default=os.environ.get("AGENTOS_CHATGPT_RUNTIME_ID", "chatgpt-web"))
    parser.add_argument("--control-plane-url", default=os.environ.get("AGENTOS_CONTROL_PLANE_URL"))
    parser.add_argument("--control-plane-token", default=os.environ.get("AGENTOS_CONTROL_PLANE_TOKEN"))
    parser.add_argument("--companion-token", default=os.environ.get("AGENTOS_CHATGPT_COMPANION_TOKEN"))
    args = parser.parse_args()

    if not args.control_plane_url:
        raise SystemExit("AGENTOS_CONTROL_PLANE_URL is required")
    if not args.companion_token:
        raise SystemExit("AGENTOS_CHATGPT_COMPANION_TOKEN is required")

    client = ControlPlaneClient(args.control_plane_url, token=args.control_plane_token)
    service = ChatGPTLocalCompanionService(client, runtime_id=args.runtime_id)
    server = ChatGPTLocalCompanionServer((args.host, args.port), service, token=args.companion_token)
    print(f"ChatGPT AgentOS companion listening on http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
