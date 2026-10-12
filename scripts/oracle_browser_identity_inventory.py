#!/usr/bin/env python3
"""#1735: read-only Oracle CDP/browser identity inventory.

Run locally on the Oracle GUI worker. Does not log in, navigate, restart,
open tabs, inspect cookies, or read page text.
"""
import json
import os
from pathlib import Path
import subprocess
import urllib.request
from urllib.parse import urlparse

PORTS = (9222, 9223, 9224)


def browser_processes(port):
    """Only process metadata; no environment, credentials or cookies."""
    found = []
    for proc in Path("/proc").iterdir():
        if not proc.name.isdigit():
            continue
        try:
            raw = (proc / "cmdline").read_bytes().split(b"\0")
            args = [a.decode("utf-8", "replace") for a in raw if a]
        except (OSError, PermissionError):
            continue
        if not any(a == f"--remote-debugging-port={port}" for a in args):
            continue
        profile = next((a.split("=", 1)[1] for a in args if a.startswith("--user-data-dir=")), None)
        found.append({"pid": int(proc.name), "profile": profile or "UNSPECIFIED"})
    return found


def targets(port):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=3) as response:
            rows = json.load(response)
        hosts = sorted(set(urlparse(str(r.get("url", ""))).hostname or "" for r in rows
                           if isinstance(r, dict) and r.get("type") == "page"))
        return {"state": "CDP_READY", "page_hosts": [h for h in hosts if h]}
    except Exception as exc:
        return {"state": "CDP_UNAVAILABLE", "error_type": type(exc).__name__}


def main():
    records = []
    for port in PORTS:
        processes = browser_processes(port)
        records.append({"port": port, "processes": processes, **targets(port)})
    profiles = [(row["port"], p["profile"]) for row in records for p in row["processes"]
                if p["profile"] != "UNSPECIFIED"]
    reused = sorted(set(p for _, p in profiles if sum(q == p for _, q in profiles) > 1))
    print(json.dumps({"schema": "agentos.browser_inventory/1", "issue": 1735,
                      "read_only": True, "records": records,
                      "shared_profiles": reused,
                      "classification": "REVIEW_REQUIRED" if reused else "UNVERIFIED"},
                     ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
