#!/usr/bin/env python3
import os
import sys
import shutil
import re
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = os.getenv("AGENT_PROJECT_ROOT", os.getcwd())
SYNC_FILE = os.path.join(PROJECT_ROOT, "memory/session_sync.md")
ARCHIVE_DIR = os.path.join(PROJECT_ROOT, "memory/archive")
AGENT_DATA_ROOT = os.getenv("AGENT_DATA_ROOT", os.path.expanduser("~/agent-data"))

SECRET_PATTERNS = [
    re.compile(r"(key=)[A-Za-z0-9_\-]{20,}", re.I),
    re.compile(r"(api[_-]?key\s*[:=]\s*)[A-Za-z0-9_\-]{12,}", re.I),
    re.compile(r"(token\s*[:=]\s*)[A-Za-z0-9_\-:.]{12,}", re.I),
    re.compile(r"AIza[0-9A-Za-z_\-]{20,}"),
]


def sanitize(text: str) -> str:
    result = text
    for pattern in SECRET_PATTERNS:
        result = pattern.sub(lambda m: f"{m.group(1)}[REDACTED]" if m.groups() else "[REDACTED]", result)
    return result


def read_text(path: str | Path, limit: int | None = None) -> str:
    p = Path(path)
    if not p.exists():
        return ""
    content = p.read_text(encoding="utf-8", errors="replace")
    return content[-limit:] if limit else content


def extract_recent_signals(content: str, limit: int = 18) -> list[str]:
    signals: list[str] = []
    for raw_line in sanitize(content).splitlines():
        line = raw_line.strip()
        if not line:
            continue
        high_signal = (
            line.startswith("## ")
            or line.startswith("> **Watchdog")
            or "**Watchdog" in line
            or "Handover" in line
            or "Service `" in line
            or "✅" in line
            or "❌" in line
            or "⚠️" in line
        )
        if not high_signal:
            continue
        line = re.sub(r"\s+", " ", line)
        if len(line) > 220:
            line = line[:217] + "..."
        if line not in signals:
            signals.append(line)
        if len(signals) >= limit:
            break
    return signals


def project_state_lines(limit: int = 24) -> list[str]:
    try:
        import sys as _sys
        root = str(Path(PROJECT_ROOT).resolve())
        if root not in _sys.path:
            _sys.path.insert(0, root)
        from agent_core.project_store import list_projects
        projects = sorted(list_projects(), key=lambda p: (-p.priority, p.project_id))
        return [
            f"- `{p.project_id}`: P{p.priority} | {p.phase} | {p.status} | {p.health.freshness}"
            for p in projects[:limit]
        ]
    except Exception as e:
        return [f"- Project state unavailable: {e}"]


def build_snapshot(original: str, archive_path: str) -> str:
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    recent_tail = original[-20000:]
    latest_report_dir = Path(AGENT_DATA_ROOT) / "journals" / "ecosystem_reports"
    reports = sorted(latest_report_dir.glob("*.md"), key=lambda p: p.stat().st_mtime) if latest_report_dir.exists() else []
    latest_report = reports[-1] if reports else None
    report_content = read_text(latest_report, 8000) if latest_report else ""

    signals = extract_recent_signals(recent_tail, 18)
    report_signals = extract_recent_signals(report_content, 10)

    return "\n".join([
        "# 🧠 AgentOS Session Sync - Compressed Working Memory",
        "> This file is the active high-density memory buffer. Raw history is archived; do not paste full logs back here.",
        "",
        f"- **Compressed At**: {now}",
        f"- **Archive Link**: `{archive_path}`",
        f"- **Source Size**: {len(original.encode('utf-8')) / 1024:.2f} KB",
        "",
        "## 🧠 Core Decisions",
        "- Logic/Data separation remains the primary invariant: code in `agentmanager`, truth/state in `agent-data`.",
        "- Knowledge Palace is the distilled LLM Wiki; raw logs must be internalized or archived instead of treated as working memory.",
        "- Status aggregation now uses `agent_core.project_store` with `project.yaml` plus legacy `STATUS.md` fallback.",
        "",
        "## 📂 Active Project States",
        *project_state_lines(),
        "",
        "## 🛠️ Infrastructure Changes And Signals",
        *(report_signals or ["- No recent ecosystem report signals found."]),
        "",
        "## ⏳ Recent Session Signals",
        *(signals or ["- No high-signal recent session lines found."]),
        "",
        "## 🔒 Privacy Note",
        "- Secrets matching common API key/token patterns were redacted during compression.",
        "",
    ])

def main():
    if not os.path.exists(SYNC_FILE):
        print("❌ No session_sync.md found.")
        return

    size_kb = os.path.getsize(SYNC_FILE) / 1024
    print(f"📊 Current Sync Buffer Size: {size_kb:.2f} KB")

    # 手動或自動觸發
    if size_kb < 30 and "--force" not in sys.argv:
        print("✅ Buffer size is healthy. No compression needed.")
        return

    print("🚀 Triggering AI Memory Compression...")
    
    # 1. Archive
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    archive_path = os.path.join(ARCHIVE_DIR, f"session_sync_{timestamp}.md")
    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    shutil.copy2(SYNC_FILE, archive_path)
    print(f"📦 Original archived to {archive_path}")

    # 2. Deterministic compression
    original = read_text(SYNC_FILE)
    compressed = build_snapshot(original, archive_path)
    with open(SYNC_FILE, "w", encoding="utf-8") as f:
        f.write(compressed)

    new_size_kb = os.path.getsize(SYNC_FILE) / 1024
    print(f"✅ Compressed active sync buffer to {new_size_kb:.2f} KB")

if __name__ == "__main__":
    main()
