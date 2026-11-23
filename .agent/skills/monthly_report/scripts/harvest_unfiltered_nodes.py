#!/usr/bin/env python3
"""Unfiltered Cross-Node Monthly Activity & Conversation Harvester.

Design Rule (Zero-Filter Harvest -> Human Review Gate):
- Never pre-exclude conversations during collection (prevents losing DQA work
  such as VPP tests conducted inside multi-purpose Codex/Claude/Gemini sessions).
- Dispatches read-only collection across registered nodes (dqa03backup, dqa03restore,
  vopc5750) via Realm Fabric and persists raw inventory for Human Review Gate filtering.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

DEFAULT_NODES: dict[str, tuple[str, str]] = {
    "dqa03backup": ("/usr/bin/python3", "/home/dqa03"),
    "dqa03restore": ("/usr/bin/python3", "/home/dqa03/AgentOS"),
    "vopc5750": (
        r"C:\Users\alston.huang\AppData\Local\Programs\Python\Python312\python.exe",
        r"C:\Users\alston.huang\AgentOS",
    ),
}


def build_remote_scan_script(year: int, month: int) -> str:
    return f"""
import json, os, datetime, re
from pathlib import Path

cutoff = datetime.datetime({year}, {month}, 1).timestamp()
home = Path(os.environ.get("USERPROFILE") or os.path.expanduser("~"))
entries = []

def scan_jsonl(f: Path, source: str):
    try:
        st = f.stat()
        if st.st_mtime < cutoff:
            return
        dt = datetime.datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d")
        snippets = []
        with open(f, "r", encoding="utf-8", errors="ignore") as fp:
            for i, line in enumerate(fp):
                if i > 1200:
                    break
                if len(snippets) < 2 and ('"role":"user"' in line or '"role": "user"' in line or '"type":"user"' in line):
                    for pat in (r'"text"\\s*:\\s*"([^"]{{6,160}})"', r'"content"\\s*:\\s*"([^"]{{6,160}})"'):
                        m = re.search(pat, line)
                        if m:
                            cand = m.group(1).replace("\\\\n", " ").strip()
                            if not cand.startswith(("# AGENTS", "<environment", "You are", "AgentOS ONE")):
                                snippets.append(cand[:100])
                                break
        entries.append({{"date": dt, "source": source, "file": f.name[:40], "preview": " | ".join(snippets) or "(tool/system)"}})
    except Exception:
        pass

for d, src in [(home / ".codex" / "sessions", "codex"), (home / ".claude" / "projects", "claude")]:
    if d.is_dir():
        for f in sorted(d.rglob("*.jsonl")):
            scan_jsonl(f, f"{{src}}:{{f.parent.name[:20]}}" if src == "claude" else src)

entries.sort(key=lambda x: x["date"], reverse=True)
print(json.dumps({{"total": len(entries), "entries": entries[:80]}}, ensure_ascii=True))
""".strip()


def harvest_all_nodes(
    year: int,
    month: int,
    *,
    receipts_db: Path = Path("/home/ubuntu/agent-data/realm/receipts.sqlite3"),
    wait_seconds: int = 10,
) -> dict[str, Any]:
    script = build_remote_scan_script(year, month)
    task_ids: dict[str, str] = {}
    for nid, (exe, cwd) in DEFAULT_NODES.items():
        tid = f"task-mrep-harvest-{nid}-{uuid.uuid4().hex[:8]}"
        payload = {
            "schema": "agentos.node-task/v0.1",
            "task_id": tid,
            "action": "shell.exec",
            "executable": exe,
            "argv": ["-c", script],
            "cwd": cwd,
            "timeout_seconds": 45,
        }
        tf = Path(f"/tmp/{tid}.json")
        tf.write_text(json.dumps(payload), encoding="utf-8")
        subprocess.run(
            ["python3", "-m", "agent_core.realm_cli", "task", "--node-id", nid, "--task-file", str(tf)],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        task_ids[nid] = tid

    time.sleep(wait_seconds)
    con = sqlite3.connect(str(receipts_db))
    results: dict[str, Any] = {}
    for nid, tid in task_ids.items():
        row = con.execute("SELECT * FROM receipts WHERE task_id = ?", (tid,)).fetchone()
        if not row:
            results[nid] = {"status": "timeout", "task_id": tid}
            continue
        d = json.loads(row[2])
        out = d.get("stdout", "").strip()
        try:
            results[nid] = json.loads(out)
        except Exception:
            results[nid] = {"status": "parse_error", "raw": out[:200]}
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Harvest unfiltered monthly conversations across DQA nodes")
    parser.add_argument("year", type=int)
    parser.add_argument("month", type=int)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    data = harvest_all_nodes(args.year, args.month)
    rendered = json.dumps(data, indent=2, ensure_ascii=False)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
