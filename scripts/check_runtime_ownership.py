#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / ".agent" / "governance" / "runtime_ownership.json"
BASE = sys.argv[1] if len(sys.argv) > 1 else "origin/main"
HEAD = sys.argv[2] if len(sys.argv) > 2 else "HEAD"

policy = json.loads(REGISTRY.read_text(encoding="utf-8"))
shared = str(policy["shared_source_checkout"]["path"])

diff = subprocess.run(
    ["git", "diff", "--unified=0", f"{BASE}...{HEAD}", "--", ".github/workflows", "scripts", "agent_core", "agentos_node"],
    check=True,
    capture_output=True,
    text=True,
).stdout

files: dict[str, list[tuple[int, str]]] = {}
current = None
new_line = 0
for line in diff.splitlines():
    if line.startswith("+++ b/"):
        current = line[6:]
        files.setdefault(current, [])
        continue
    if line.startswith("@@"):
        match = re.search(r"\+(\d+)", line)
        new_line = int(match.group(1)) if match else 0
        continue
    if current is None:
        continue
    if line.startswith("+") and not line.startswith("+++"):
        files[current].append((new_line, line[1:]))
        new_line += 1
    elif not line.startswith("-"):
        new_line += 1

violations: list[str] = []
dangerous_git = re.compile(r"\bgit\b[^\n]*(?:checkout|switch|pull|reset\s+--hard|clean\b)", re.I)
copy_into_shared = re.compile(r"\b(?:cp|mv|rsync)\b[^\n]*(?:/home/ubuntu/agentmanager|\$\{?(?:ROOT|APP_ROOT|AGENT_ROOT)\}?)", re.I)
live_runtime = re.compile(r"(?:WorkingDirectory|ExecStart)\s*=.*?/home/ubuntu/agentmanager(?:/|\b)", re.I)
process_manager_runtime = re.compile(
    r"\b(?:pm2|node\s+[^\n]*pm2[^\n]*)\b[^\n]*--cwd\s+(?:[\"']?)"
    + re.escape(shared)
    + r"(?:/|\b)",
    re.I,
)

for path, additions in files.items():
    p = ROOT / path
    if p.resolve() == Path(__file__).resolve():
        continue
    full = p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""
    aliases = set(
        re.findall(
            r"(?m)^\s*([A-Z][A-Z0-9_]*)=(?:[\"'])?"
            + re.escape(shared)
            + r"(?:/[^\s\"']*)?(?:[\"'])?\s*$",
            full,
        )
    )
    alias_expr = "|".join(re.escape(name) for name in sorted(aliases))
    alias_git = (
        re.compile(
            r"\bgit\s+-C\s+(?:[\"']?\$\{?(?:" + alias_expr + r")\}?[\"']?)[^\n]*(?:checkout|switch|pull|reset\s+--hard|clean\b)",
            re.I,
        )
        if aliases
        else None
    )
    alias_process_runtime = (
        re.compile(
            r"\b(?:pm2|node\s+[^\n]*pm2[^\n]*)\b[^\n]*--cwd\s+(?:[\"']?\$\{?(?:"
            + alias_expr
            + r")\}?[\"']?)",
            re.I,
        )
        if aliases
        else None
    )

    for line_no, added in additions:
        stripped = added.strip()
        reason = None
        if shared in added and dangerous_git.search(added):
            reason = "mutates shared AgentOS checkout"
        elif alias_git and alias_git.search(added):
            reason = "mutates shared AgentOS checkout through an alias"
        elif shared in added and copy_into_shared.search(added):
            reason = "copies/moves files into shared AgentOS checkout"
        elif live_runtime.search(added):
            reason = "declares production runtime directly from mutable shared checkout"
        elif process_manager_runtime.search(added):
            reason = "launches a process manager from mutable shared checkout"
        elif alias_process_runtime and alias_process_runtime.search(added):
            reason = "launches a process manager from mutable shared checkout through an alias"

        if reason:
            violations.append(f"{path}:{line_no}: {reason}: {stripped[:180]}")

if violations:
    print("RUNTIME_OWNERSHIP_GUARD=FAIL")
    for item in violations:
        print(item)
    print("Use a service-specific immutable release directory + live pointer from .agent/governance/runtime_ownership.json.")
    raise SystemExit(2)

print("RUNTIME_OWNERSHIP_GUARD=PASS")
print(f"shared_checkout={shared} role=source-cache-only")
