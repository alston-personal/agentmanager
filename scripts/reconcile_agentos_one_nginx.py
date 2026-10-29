#!/usr/bin/env python3
"""Safely reconcile the dedicated AgentOS ONE Nginx proxy with the governed port 3000."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

CONFIG = Path("/etc/nginx/sites-available/studio.milkcat.org")
TARGET = "http://127.0.0.1:3000"
OLD = "http://127.0.0.1:3041"
HEALTH = "https://studio.milkcat.org/dashboard/api/agentos/v1/health"
LOCAL = "http://127.0.0.1:3000/dashboard/api/agentos/v1/health"

def run(*cmd: str) -> str:
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=25)
    if p.returncode:
        raise RuntimeError(f"{cmd[0]} failed (exit {p.returncode}): {p.stderr[-300:]}")
    return p.stdout

def probe(url: str) -> dict:
    body = run("curl", "-fsS", "--max-time", "8", url)
    result = json.loads(body)
    if result.get("ok") is not True or result.get("realm_id") != "realm-alston":
        raise RuntimeError("Unexpected ONE health identity")
    return result

def main() -> None:
    probe(LOCAL)
    if not CONFIG.is_file():
        raise RuntimeError("Expected Nginx configuration missing; refusing unrelated config edits")
    source = CONFIG.read_text()
    # Only change a dedicated AgentOS route, never a generic /dashboard or / location.
    matches = list(re.finditer(r"(?m)^\s*location\s+(?:\^~\s+|=\s+)?(/dashboard/api/agentos/[^\s{]*|/dashboard/api/agentos)\s*\{", source))
    if len(matches) != 1:
        raise RuntimeError(f"Expected exactly one dedicated AgentOS location, found {len(matches)}")
    m = matches[0]
    start = m.end()
    level = 1
    end = start
    while end < len(source) and level:
        if source[end] == "{":
            level += 1
        elif source[end] == "}":
            level -= 1
        end += 1
    if level:
        raise RuntimeError("Unbalanced Nginx location")
    block = source[start:end-1]
    old_count = block.count(OLD)
    new_count = block.count(TARGET)
    if old_count == 0 and new_count == 1:
        probe(HEALTH)
        print(json.dumps({"ok":True,"changed":False,"public_health":"PASS"}))
        return
    if old_count != 1 or new_count:
        raise RuntimeError("Unexpected or ambiguous proxy_pass; refusing mutation")
    updated = source[:start] + block.replace(OLD, TARGET, 1) + source[end-1:]
    backup = CONFIG.with_name(CONFIG.name + ".agentos-one." + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ".bak")
    shutil.copy2(CONFIG, backup)
    try:
        CONFIG.write_text(updated)
        run("nginx", "-t")
        run("systemctl", "reload", "nginx")
        probe(HEALTH)
    except Exception:
        shutil.copy2(backup, CONFIG)
        run("nginx", "-t")
        run("systemctl", "reload", "nginx")
        raise
    print(json.dumps({"ok":True,"changed":True,"public_health":"PASS","backup":backup.name}))

if __name__ == "__main__":
    main()
