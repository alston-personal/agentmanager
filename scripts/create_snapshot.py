#!/usr/bin/env python3
import os
from datetime import datetime, timezone
from pathlib import Path


# Add project root to sys.path to import agent_core
PROJECT_ROOT_DETECTED = Path(__file__).resolve().parent.parent
import sys
if str(PROJECT_ROOT_DETECTED) not in sys.path:
    sys.path.append(str(PROJECT_ROOT_DETECTED))

from agent_core.memory_router import resolve_memory_route
from agentos_host.adapter import AgentOSContextAdapter

route = resolve_memory_route()
PROJECT_ROOT = route.project_root
AGENT_DATA_ROOT = route.data_root
MEMORY_ROOT = route.memory_dir
SNAPSHOT_DIR = MEMORY_ROOT / "snapshots"


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def main() -> int:
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc)
    date_stamp = now.strftime("%Y-%m-%d")
    time_stamp = now.strftime("%Y-%m-%d %H:%M UTC")
    snapshot_path = SNAPSHOT_DIR / f"{date_stamp}_SUMMARY.md"

    short_term = read_text(route.short_term_path).strip()
    long_term = read_text(route.long_term_path).strip()
    adapter = AgentOSContextAdapter(PROJECT_ROOT, AGENT_DATA_ROOT)
    session_sync = adapter.read_compact_session_sync(max_chars=6000).strip()
    latest_sessions = adapter.latest_session_records(limit=3)

    session_records_block = []
    for record in latest_sessions:
        session_records_block.append(
            f"- `{record.get('session_id', 'unknown')}` {record.get('ended_at', 'unknown')} | {record.get('summary', 'unknown')}"
        )
    latest_sessions_text = "\n".join(session_records_block) or "(none)"

    content = [
        f"# Snapshot Summary - {date_stamp}",
        "",
        f"- Generated: {time_stamp}",
        f"- Data Root: `{AGENT_DATA_ROOT}`",
        "",
        "## Short Term Memory",
        short_term or "(empty)",
        "",
        "## Session Sync",
        session_sync or "(empty)",
        "",
        "## Latest Session Records",
        latest_sessions_text,
        "",
        "## Long Term Memory",
        long_term or "(empty)",
        "",
    ]

    snapshot_path.write_text("\n".join(content), encoding="utf-8")
    print(snapshot_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
