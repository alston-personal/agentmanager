#!/usr/bin/env python3
import os
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path("/home/ubuntu/agentmanager")
AGENT_DATA_ROOT = Path(os.environ.get("AGENT_DATA_ROOT", "/home/ubuntu/agent-data"))
MEMORY_ROOT = AGENT_DATA_ROOT / "memory"
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

    short_term = read_text(MEMORY_ROOT / "SHORT_TERM.md").strip()
    long_term = read_text(MEMORY_ROOT / "LONG_TERM.md").strip()
    session_sync = read_text(MEMORY_ROOT / "session_sync.md").strip()

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
        "## Long Term Memory",
        long_term or "(empty)",
        "",
    ]

    snapshot_path.write_text("\n".join(content), encoding="utf-8")
    print(snapshot_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
