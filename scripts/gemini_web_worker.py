#!/usr/bin/env python3
"""Run the isolated Linux Gemini Web relay.

This process is intended for a dedicated browser-worker Linux user/container.
It must not run as AgentOS Core and must not expose browser profile contents.
"""

from __future__ import annotations

import argparse
import os

from agentos_node.gemini_web_worker import (
    GeminiWebRelay,
    GeminiWebRelayServer,
    PlaywrightGeminiSession,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=os.getenv("AGENTOS_GEMINI_WEB_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("AGENTOS_GEMINI_WEB_PORT", "8785")))
    parser.add_argument(
        "--provider-id",
        default=os.getenv("AGENTOS_GEMINI_WEB_PROVIDER_ID", "gemini-web-shadow"),
    )
    parser.add_argument(
        "--profile-dir",
        default=os.getenv("AGENTOS_GEMINI_WEB_PROFILE_DIR"),
    )
    parser.add_argument(
        "--browser-executable",
        default=os.getenv("AGENTOS_GEMINI_WEB_BROWSER"),
    )
    parser.add_argument("--headless", action="store_true")
    args = parser.parse_args()

    if not args.profile_dir:
        parser.error("--profile-dir or AGENTOS_GEMINI_WEB_PROFILE_DIR is required")

    session = PlaywrightGeminiSession(
        profile_dir=args.profile_dir,
        browser_executable=args.browser_executable,
        headless=args.headless,
    )
    relay = GeminiWebRelay(session, provider_id=args.provider_id)
    server = GeminiWebRelayServer(
        (args.host, args.port),
        relay,
        token=os.getenv("AGENTOS_GEMINI_WEB_TOKEN"),
    )
    print(
        f"AgentOS Gemini Web worker listening on http://{args.host}:{args.port} "
        f"provider={args.provider_id} profile=<isolated>"
    )
    try:
        server.serve_forever()
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
