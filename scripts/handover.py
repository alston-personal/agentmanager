#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from agent_core.session_lifecycle import close_session
from agentos_host.adapter import AgentOSContextAdapter


def main() -> int:
    parser = argparse.ArgumentParser(description="Close the active AgentOS session and emit a compact handover")
    parser.add_argument("--project-root", default=None)
    parser.add_argument("--data-root", default=None)
    parser.add_argument("--summary", default=None)
    parser.add_argument("--agent", default=None)
    args = parser.parse_args()

    adapter = AgentOSContextAdapter(
        project_root=Path(args.project_root) if args.project_root else Path(PROJECT_ROOT).expanduser().resolve(),
        data_root=Path(args.data_root) if args.data_root else Path(os.environ.get("AGENT_DATA_ROOT", "~/agent-data")).expanduser().resolve()
    )
    result = close_session(
        context_provider=adapter,
        agent_name=args.agent,
        summary=args.summary,
        project_root=Path(args.project_root) if args.project_root else None,
        data_root=Path(args.data_root) if args.data_root else None,
    )
    print(result.compact_entry)
    print(f"Record: {result.record_uri}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
