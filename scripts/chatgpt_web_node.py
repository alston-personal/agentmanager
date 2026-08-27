#!/usr/bin/env python3
"""Emit a ChatGPT Web AgentOS bootstrap/resume packet as JSON."""

from __future__ import annotations

import argparse
import json
import os
import sys

from agentos_node.chatgpt_web_node import bootstrap_chatgpt_web
from agentos_node.control_plane_client import ControlPlaneClient


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_id", help="stable AgentOS project id to resume")
    parser.add_argument("--runtime-id", default="chatgpt-web")
    parser.add_argument(
        "--control-plane-url",
        default=os.environ.get("AGENTOS_CONTROL_PLANE_URL"),
        help="defaults to AGENTOS_CONTROL_PLANE_URL",
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("AGENTOS_CONTROL_PLANE_TOKEN"),
        help="defaults to AGENTOS_CONTROL_PLANE_TOKEN",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.control_plane_url:
        raise SystemExit("AGENTOS_CONTROL_PLANE_URL or --control-plane-url is required")

    client = ControlPlaneClient(args.control_plane_url, token=args.token)
    packet = bootstrap_chatgpt_web(client, args.project_id, runtime_id=args.runtime_id)
    json.dump(packet.to_dict(), sys.stdout, ensure_ascii=False, sort_keys=True, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
