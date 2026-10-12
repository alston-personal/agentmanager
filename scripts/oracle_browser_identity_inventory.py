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
        has_port = any(a == f"--remote-debugging-port={port}" or
                       (a == "--remote-debugging-port" and i + 1 < len(args) and args[i + 1] == str(port))
                       for i, a in enumerate(args))
        if not has_port:
            continue
        path = next((a.split("=", 1)[1] for a in args
                     if a.startswith("--user-data-dir=")), None)
        if path is None and "--user-data-dir" in args:
            index = args.index("--user-data-dir")
            path = args[index + 1] if index + 1 < len(args) else None
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



def process_visibility():
    """Aggregate /proc visibility only; never emit argv, paths, or identities."""
    result = {"pid_entries": 0, "cmdline_readable": 0,
              "cmdline_permission_denied": 0, "cmdline_other_errors": 0,
              "chromium_like_processes": 0}
    try:
        entries = Path("/proc").iterdir()
        for proc in entries:
            if not proc.name.isdigit():
                continue
            result["pid_entries"] += 1
            try:
                raw = (proc / "cmdline").read_bytes()
            except PermissionError:
                result["cmdline_permission_denied"] += 1
                continue
            except OSError:
                result["cmdline_other_errors"] += 1
                continue
            result["cmdline_readable"] += 1
            # Inspect executable basename only in memory; never output its value.
            first = raw.split(b"\0", 1)[0].rsplit(b"/", 1)[-1].lower()
            if any(tag in first for tag in (b"chrom", b"brave", b"edge")):
                result["chromium_like_processes"] += 1
    except OSError:
        result["proc_scan_error"] = True
    return result



def cdp_launch_hints():
    """Count only launch-flag categories, not flag values, argv, or identities."""
    counts = {"debugging_port_flag": 0, "debugging_pipe_flag": 0,
              "profile_flag": 0, "browser_processes": 0,
              "proxy_like_processes": 0, "unknown_process_argv": 0}
    try:
        procs = Path("/proc").iterdir()
        for proc in procs:
            if not proc.name.isdigit():
                continue
            try:
                data = (proc / "cmdline").read_bytes()
            except OSError:
                counts["unknown_process_argv"] += 1
                continue
            argv = [p.decode("utf-8", "replace") for p in data.split(b"\0") if p]
            if not argv:
                continue
            exe = argv[0].rsplit("/", 1)[-1].lower()
            browser = any(tag in exe for tag in ("chrom", "brave", "msedge"))
            proxy = exe in {"socat", "nginx", "haproxy", "ssh", "websockify"}
            if proxy:
                counts["proxy_like_processes"] += 1
            if not browser:
                continue
            counts["browser_processes"] += 1
            if any(arg == "--remote-debugging-port" or arg.startswith("--remote-debugging-port=")
                   for arg in argv):
                counts["debugging_port_flag"] += 1
            if "--remote-debugging-pipe" in argv:
                counts["debugging_pipe_flag"] += 1
            if any(arg == "--user-data-dir" or arg.startswith("--user-data-dir=")
                   for arg in argv):
                counts["profile_flag"] += 1
    except OSError:
        counts["proc_scan_error"] = True
    return counts


def visibility_classification(records, stats):
    """Hints only: no heuristic verifies an account, profile, or namespace."""
    if stats.get("proc_scan_error"):
        return "PROC_SCAN_UNAVAILABLE"
    if any(r["processes"] for r in records):
        return "PORT_PROCESS_OBSERVED"
    if stats["cmdline_permission_denied"]:
        return "PROCESS_PERMISSION_OR_ISOLATION_POSSIBLE"
    if stats["chromium_like_processes"]:
        return "BROWSER_VISIBLE_PORT_MAPPING_UNRESOLVED"
    if any(r["state"] == "CDP_READY" for r in records):
        return "CDP_READY_BROWSER_PROCESS_NOT_VISIBLE"
    return "CDP_AND_BROWSER_PROCESS_UNAVAILABLE"


def inventory():
    records = [{"port": port, "processes": browser_processes(port), **targets(port)}
               for port in PORTS]
    identities = [(r["port"], p["profile_id"]) for r in records
                  for p in r["processes"] if p["profile_id"]]
    shared = sorted({p for _, p in identities if len({port for port, q in identities if q == p}) > 1})
    visibility = process_visibility()
    launch_hints = cdp_launch_hints()
    return {"schema": "agentos.browser_inventory/1", "issue": 1735,
            "read_only": True, "records": records, "shared_profile_ids": shared,
            "process_visibility": visibility,
            "cdp_launch_hints": launch_hints,
            "process_visibility_classification": visibility_classification(records, visibility),
            "classification": "REVIEW_REQUIRED" if shared else "UNVERIFIED",
            "account_identity_verified": False}


if __name__ == "__main__":
    print(json.dumps(inventory(), ensure_ascii=False, sort_keys=True))
