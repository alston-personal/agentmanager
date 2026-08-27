#!/usr/bin/env python3
"""Resume an AgentOS project in ChatGPT through the external ai-browser-bridge."""

from __future__ import annotations

import argparse
import json
import os
import sys

from agentos_node.ai_browser_bridge import AiBrowserBridgeClient
from agentos_node.chatgpt_browser_resume import resume_via_browser
from agentos_node.control_plane_client import ControlPlaneClient


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_id", help="stable AgentOS project id to resume")
    parser.add_argument("--intent", default="continue", help="original continuation intent")
    parser.add_argument("--runtime-id", default="chatgpt-web")
    parser.add_argument("--bridge", default=os.environ.get("AGENTOS_BROWSER_BRIDGE", "bridge"))
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument(
        "--control-plane-url",
        default=os.environ.get("AGENTOS_CONTROL_PLANE_URL"),
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("AGENTOS_CONTROL_PLANE_TOKEN"),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.control_plane_url:
        raise SystemExit("AGENTOS_CONTROL_PLANE_URL or --control-plane-url is required")

    control_plane = ControlPlaneClient(args.control_plane_url, token=args.token)
    bridge = AiBrowserBridgeClient(executable=args.bridge)
    result = resume_via_browser(
        control_plane,
        bridge,
        args.project_id,
        runtime_id=args.runtime_id,
        user_intent=args.intent,
        timeout_seconds=args.timeout,
    )
    json.dump(result.to_dict(), sys.stdout, ensure_ascii=False, sort_keys=True, indent=2)
    sys.stdout.write("\n")
    return 0 if result.bridge_reply.ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
