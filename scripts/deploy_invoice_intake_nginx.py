#!/usr/bin/env python3
from __future__ import annotations

import json
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

CONFIG = Path("/etc/nginx/sites-available/studio.milkcat.org")
BEGIN = "# BEGIN milkcat invoice intake api"
END = "# END milkcat invoice intake api"

BLOCK = r'''    # BEGIN milkcat invoice intake api
    location = /api/invoice-intake/v1/status {
        limit_except GET HEAD { deny all; }
        proxy_pass http://127.0.0.1:18766/v1/status;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header Cookie $http_cookie;
    }

    location ^~ /api/invoice-intake/v1/ {
        client_max_body_size 16m;
        rewrite ^/api/invoice-intake(/.*)$ $1 break;
        proxy_pass http://127.0.0.1:18766;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header Cookie $http_cookie;
        proxy_read_timeout 45s;
    }
    # END milkcat invoice intake api'''


def run(args: list[str], check: bool = True) -> subprocess.CompletedProcess:
    p = subprocess.run(args, text=True, capture_output=True, timeout=30)
    if check and p.returncode != 0:
        raise RuntimeError(f"command_failed:{args[0]}:{p.returncode}")
    return p


def strip_existing(text: str) -> str:
    if BEGIN not in text:
        return text
    if END not in text:
        raise RuntimeError("invoice_marker_unbalanced")
    before, rest = text.split(BEGIN, 1)
    _, after = rest.split(END, 1)
    return before.rstrip() + "\n" + after.lstrip("\n")


def brace_delta(line: str) -> int:
    return line.count("{") - line.count("}")


def find_https_server(lines: list[str]) -> int:
    depth = 0
    start = None
    server_depth = None
    candidates: list[tuple[int, int, str]] = []
    for idx, line in enumerate(lines):
        stripped = line.strip()
        before = depth
        if start is None and stripped.startswith("server") and "{" in stripped:
            start = idx
            server_depth = before + line.count("{")
        depth += brace_delta(line)
        if start is not None and server_depth is not None and depth < server_depth:
            block = "\n".join(lines[start:idx+1])
            if "server_name" in block and "studio.milkcat.org" in block and "listen" in block and "443" in block:
                candidates.append((start, idx, block))
            start = None
            server_depth = None
    if len(candidates) != 1:
        raise RuntimeError(f"studio_https_server_count:{len(candidates)}")
    return candidates[0][1]


def main() -> int:
    if not CONFIG.is_file():
        raise RuntimeError("studio_nginx_config_missing")
    original = CONFIG.read_text(encoding="utf-8")
    clean = strip_existing(original)
    lines = clean.splitlines()
    end = find_https_server(lines)
    lines.insert(end, BLOCK)
    updated = "\n".join(lines) + ("\n" if clean.endswith("\n") else "")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = CONFIG.with_name(CONFIG.name + f".invoice-intake.{stamp}.bak")
    shutil.copy2(CONFIG, backup)
    changed = updated != original

    try:
        if changed:
            CONFIG.write_text(updated, encoding="utf-8")
        run(["nginx", "-t"])
        if changed:
            run(["systemctl", "reload", "nginx"])
            time.sleep(1)
        local = run([
            "curl", "-kfsS", "--max-time", "10",
            "--resolve", "studio.milkcat.org:443:127.0.0.1",
            "https://studio.milkcat.org/api/invoice-intake/v1/status"
        ])
        public = run([
            "curl", "-fsS", "--retry", "5", "--retry-delay", "1", "--max-time", "15",
            "https://studio.milkcat.org/api/invoice-intake/v1/status"
        ])
        local_json = json.loads(local.stdout)
        public_json = json.loads(public.stdout)
        if not local_json.get("ok") or not public_json.get("ok"):
            raise RuntimeError("invoice_status_acceptance_failed")
        print(json.dumps({
            "schema": "milkcat.invoice-intake-nginx/v1",
            "ok": True,
            "changed": changed,
            "backup": backup.name,
            "local_status": local_json,
            "public_status": public_json,
        }, ensure_ascii=False, indent=2))
        return 0
    except Exception:
        if changed:
            shutil.copy2(backup, CONFIG)
            run(["nginx", "-t"])
            run(["systemctl", "reload", "nginx"])
        raise


if __name__ == "__main__":
    raise SystemExit(main())
