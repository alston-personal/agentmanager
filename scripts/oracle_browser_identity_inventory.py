#!/usr/bin/env python3
"""Read-only CDP/profile inventory for #1735; sanitized stdout only."""
import hashlib
import json
from pathlib import Path
import urllib.request
from urllib.parse import urlparse

PORTS = (9222, 9223, 9224)


def profile_id(path):
    if not path:
        return None
    return hashlib.sha256(path.encode("utf-8")).hexdigest()[:16]


def browser_processes(port):
    found = []
    try:
        processes = list(Path("/proc").iterdir())
    except OSError:
        return found
    for proc in processes:
        if not proc.name.isdigit():
            continue
        try:
            args = [v.decode("utf-8", "replace") for v in
                    (proc / "cmdline").read_bytes().split(b"\0") if v]
        except OSError:
            continue
        if f"--remote-debugging-port={port}" not in args:
            continue
        path = next((a.split("=", 1)[1] for a in args
                     if a.startswith("--user-data-dir=")), None)
        found.append({"pid": int(proc.name), "profile_id": profile_id(path),
                      "profile_explicit": bool(path)})
    return found


def targets(port):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=3) as response:
            rows = json.load(response)
        hosts = sorted({urlparse(str(r.get("url", ""))).hostname or ""
                        for r in rows if isinstance(r, dict) and r.get("type") == "page"})
        return {"state": "CDP_READY", "page_hosts": [h for h in hosts if h]}
    except Exception as exc:
        return {"state": "CDP_UNAVAILABLE", "error_type": type(exc).__name__}


def inventory():
    records = [{"port": port, "processes": browser_processes(port), **targets(port)}
               for port in PORTS]
    identities = [(r["port"], p["profile_id"]) for r in records
                  for p in r["processes"] if p["profile_id"]]
    shared = sorted({p for _, p in identities if len({port for port, q in identities if q == p}) > 1})
    return {"schema": "agentos.browser_inventory/1", "issue": 1735,
            "read_only": True, "records": records, "shared_profile_ids": shared,
            "classification": "REVIEW_REQUIRED" if shared else "UNVERIFIED",
            "account_identity_verified": False}


if __name__ == "__main__":
    print(json.dumps(inventory(), ensure_ascii=False, sort_keys=True))
