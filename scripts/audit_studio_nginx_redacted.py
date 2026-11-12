#!/usr/bin/env python3
"""Read-only, redacted Studio host audit. Never prints raw Nginx configuration or secrets."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

SITE = "studio.milkcat.org"
LEGACY = "/home/ubuntu/zeus-writer/website/dist"
CANONICAL = "/home/ubuntu/studio-web/dist"
PROBES = {
    "/": "html",
    "/world/": "html",
    "/layout-lab/": "html",
    "/wow-addons/": "html",
    "/.well-known/studio-root-authority.txt": "marker",
    "/dashboard/api/auth/session": "api-status",
}
WRITER_DIRS = (
    Path("/home/ubuntu/agentmanager/.github/workflows"),
    Path("/home/ubuntu/agentmanager/scripts"),
    Path("/home/ubuntu/agentmanager/agentos_node"),
    Path("/home/ubuntu/.config/systemd/user"),
    Path("/etc/systemd/system"),
)
READ_SUFFIXES = {".yml", ".yaml", ".sh", ".py", ".service", ".timer"}
MAX_FILE = 262144
MAX_SCAN = 4000

def root_class(value: str) -> str:
    val = value.strip().strip("'\"").rstrip("/")
    if val == LEGACY:
        return "legacy-zeuswriter"
    if val == CANONICAL:
        return "canonical-studio"
    return "other"  # Never echo arbitrary paths from production configuration.

def parse_nginx(content: str) -> list[dict]:
    """Project only approved directives from matching server blocks, never raw config."""
    blocks = []
    stack = []
    current = None
    for raw in content.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.endswith("{"):
            opener = line[:-1].strip()
            stack.append(opener)
            if opener == "server":
                current = {"name_match": False, "listens": [], "roots": [], "locations": [], "aliases": [], "proxies": [], "index_fallback": False}
            elif current is not None and opener.startswith("location "):
                # Only emit exact allowlisted public path names, not arbitrary regex content.
                loc = opener[len("location "):].strip()
                if loc in PROBES:
                    current["locations"].append(loc)
            continue
        if line == "}":
            if stack and stack[-1] == "server" and current is not None:
                if current["name_match"]:
                    current.pop("name_match")
                    blocks.append(current)
                current = None
            if stack:
                stack.pop()
            continue
        if current is None or not line.endswith(";"):
            continue
        bits = line[:-1].split(None, 1)
        if len(bits) != 2:
            continue
        key, val = bits
        if key == "server_name" and SITE in val.split():
            current["name_match"] = True
        elif key == "listen":
            # Report port/SSL only; not listening IP, hostname or optional flags.
            match = re.search(r"(?<![0-9])([0-9]{2,5})(?![0-9])", val)
            current["listens"].append({"port": int(match.group(1)) if match else None, "tls": "ssl" in val})
        elif key == "root":
            current["roots"].append(root_class(val))
        elif key == "alias":
            current["aliases"].append(root_class(val))
        elif key == "proxy_pass":
            current["proxies"].append("loopback" if re.match(r"^https?://(?:127\.0\.0\.1|localhost)(?::|/|$)", val) else "other")
        elif key == "try_files" and "/index.html" in val.split():
            current["index_fallback"] = True
    return blocks

def run_nginx() -> dict:
    try:
        cmd = subprocess.run(["/usr/sbin/nginx", "-T"], capture_output=True, text=True, timeout=12, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return {"available": False, "reason": "execution_unavailable"}
    if cmd.returncode != 0:
        return {"available": False, "reason": "read_denied_or_invalid"}
    blocks = parse_nginx(cmd.stdout)
    return {"available": True, "site_blocks": blocks, "site_found": bool(blocks)}

def scan_writers() -> dict:
    found = []
    scanned = 0
    for root in WRITER_DIRS:
        if not root.is_dir():
            continue
        for folder, dirs, files in os.walk(root):
            dirs[:] = [x for x in dirs if x not in (".git", "node_modules", ".venv", "__pycache__")]
            for name in sorted(files):
                if scanned >= MAX_SCAN:
                    return {"files_examined": scanned, "limit_reached": True, "references": found}
                p = Path(folder) / name
                if p.suffix not in READ_SUFFIXES or p.is_symlink():
                    continue
                try:
                    if p.stat().st_size > MAX_FILE:
                        continue
                    raw = p.read_text(encoding="utf-8", errors="replace")
                except (OSError, ValueError):
                    continue
                scanned += 1
                if LEGACY in raw:
                    # Relative code file name or unit basename only; no file content, env or credentials.
                    label = str(p.relative_to(root)) if "agentmanager" in str(root) else p.name
                    found.append({"scope": "agentmanager" if "agentmanager" in str(root) else "unit", "file": label[:160]})
    return {"files_examined": scanned, "limit_reached": False, "references": found}

def probe(path: str, kind: str) -> dict:
    command = [
        "/usr/bin/curl", "--silent", "--show-error", "--max-time", "10",
        "--resolve", f"{SITE}:443:127.0.0.1", "--output", "/dev/null",
        "--write-out", "%{http_code}|%{content_type}|%{redirect_url}",
        f"https://{SITE}{path}",
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=12, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return {"path": path, "reachable": False, "status": None}
    pieces = result.stdout.strip().split("|", 2)
    status = int(pieces[0]) if pieces and pieces[0].isdigit() else None
    ctype = pieces[1].split(";")[0] if len(pieces) > 1 else ""
    observation = {
        "path": path,
        "reachable": result.returncode == 0,
        "status": status,
        "html_mime": ctype == "text/html" if kind == "html" else None,
        "redirect": bool(pieces[2]) if len(pieces) > 2 else False,
        "content_identity_checked": kind == "marker",
    }
    if kind == "marker" and status == 200:
        try:
            marker = subprocess.run([
                "/usr/bin/curl", "--silent", "--max-time", "8", "--max-filesize", "256",
                "--resolve", f"{SITE}:443:127.0.0.1", f"https://{SITE}{path}"
            ], capture_output=True, timeout=10, check=False)
            observation["canonical_marker_match"] = (
                marker.returncode == 0 and marker.stdout.strip() == b"studio-web-production-root/v1"
            )
        except (OSError, subprocess.TimeoutExpired):
            observation["canonical_marker_match"] = False
    return observation

def main() -> int:
    report = {
        "schema": "studio.nginx-redacted-audit/v1",
        "read_only": True,
        "production_mutations": False,
        "nginx": run_nginx(),
        "legacy_path_references": scan_writers(),
        "origin_probes": [probe(path, kind) for path, kind in PROBES.items()],
    }
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    # Unavailable live config is a hard blocker; an old root is an observation, not an audit failure.
    return 0 if report["nginx"].get("site_found") else 2

if __name__ == "__main__":
    sys.exit(main())
