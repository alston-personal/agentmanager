#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

SERVICE_NAME = "model2ir-lab.service"
SERVICE_PORT = 18766
RUNTIME_ROOT = Path("/opt/model2ir-lab")
CURRENT_LINK = RUNTIME_ROOT / "current"
SYSTEMD_UNIT = Path("/etc/systemd/system") / SERVICE_NAME
STATIC_TARGET = Path("/home/ubuntu/zeus-writer/website/dist/poc/model2ir-lab")
NGINX_CONFIG = Path("/etc/nginx/sites-available/studio.milkcat.org")
MARKER_BEGIN = "# BEGIN milkcat model2ir lab v0.1"
MARKER_END = "# END milkcat model2ir lab v0.1"
PUBLIC_BASE = "https://studio.milkcat.org"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")

NGINX_BLOCK = r'''    # BEGIN milkcat model2ir lab v0.1
    location = /api/model2ir/v1/healthz {
        limit_except GET HEAD { deny all; }
        proxy_pass http://127.0.0.1:18766/healthz;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 10s;
    }

    location = /api/model2ir/v1/analyze {
        limit_except POST { deny all; }
        client_max_body_size 32m;
        proxy_pass http://127.0.0.1:18766/v1/analyze;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Model2IR-Filename $http_x_model2ir_filename;
        proxy_request_buffering on;
        proxy_connect_timeout 5s;
        proxy_read_timeout 45s;
        proxy_send_timeout 45s;
    }
    # END milkcat model2ir lab v0.1'''

UNIT = f'''[Unit]
Description=Model2IR Lab v0.1 localhost analysis service
After=network.target

[Service]
Type=simple
User=ubuntu
Group=ubuntu
Environment=PYTHONPATH={CURRENT_LINK}/lib
Environment=PYTHONDONTWRITEBYTECODE=1
ExecStart=/usr/bin/python3 {CURRENT_LINK}/model2ir_lab_server.py --host 127.0.0.1 --port {SERVICE_PORT}
Restart=on-failure
RestartSec=2
TimeoutStartSec=20
TimeoutStopSec=10
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictSUIDSGID=true
LockPersonality=true
CapabilityBoundingSet=
AmbientCapabilities=
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
MemoryMax=1G
TasksMax=64

[Install]
WantedBy=multi-user.target
'''


def run(args: list[str], *, check: bool = True, timeout: int = 45) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout)
    if check and proc.returncode != 0:
        raise RuntimeError(f"command failed: {args[0]} rc={proc.returncode} stderr_length={len(proc.stderr or '')}")
    return proc


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def brace_delta(line: str) -> int:
    return line.count("{") - line.count("}")


def find_studio_https_server(lines: list[str]) -> tuple[int, int]:
    depth = 0
    server_start = None
    server_depth = None
    candidates: list[tuple[int, int, bool, bool]] = []
    for idx, line in enumerate(lines):
        stripped = line.strip()
        before = depth
        if server_start is None and stripped.startswith("server") and "{" in stripped:
            server_start = idx
            server_depth = before + line.count("{")
        depth += brace_delta(line)
        if server_start is not None and server_depth is not None and depth < server_depth:
            block = "\n".join(lines[server_start : idx + 1])
            if "server_name" in block and "studio.milkcat.org" in block:
                listens = []
                for raw in block.splitlines():
                    s = raw.strip()
                    if s.startswith("listen ") and ";" in s:
                        listens.append(s[len("listen ") :].split(";", 1)[0].strip())
                is_443 = any(x == "443" or x.startswith("443 ") or x.startswith("[::]:443") for x in listens)
                has_studio_identity = "location /api/cookies" in block or "location = /api/cookies" in block
                candidates.append((server_start, idx, is_443, has_studio_identity))
            server_start = None
            server_depth = None
    https = [x for x in candidates if x[2]]
    identified = [x for x in https if x[3]]
    if len(identified) == 1:
        return identified[0][0], identified[0][1]
    if len(https) == 1:
        return https[0][0], https[0][1]
    if len(https) > 1:
        raise RuntimeError("multiple Studio HTTPS server blocks found")
    raise RuntimeError("Studio HTTPS server block not found")


def strip_marker(text: str) -> str:
    if MARKER_BEGIN not in text:
        return text
    if MARKER_END not in text:
        raise RuntimeError("Model2IR nginx marker begin exists without end")
    before, rest = text.split(MARKER_BEGIN, 1)
    _, after = rest.split(MARKER_END, 1)
    return before.rstrip() + "\n" + after.lstrip("\n")


def install_nginx_block() -> tuple[bool, Path]:
    if not NGINX_CONFIG.is_file():
        raise RuntimeError("Studio nginx config missing")
    original = NGINX_CONFIG.read_text(encoding="utf-8")
    clean = strip_marker(original)
    lines = clean.splitlines()
    _, server_end = find_studio_https_server(lines)
    lines.insert(server_end, NGINX_BLOCK)
    updated = "\n".join(lines) + ("\n" if clean.endswith("\n") else "")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = NGINX_CONFIG.with_name(NGINX_CONFIG.name + f".model2ir-lab.{stamp}.bak")
    shutil.copy2(NGINX_CONFIG, backup)
    changed = updated != original
    if changed:
        NGINX_CONFIG.write_text(updated, encoding="utf-8")
    run(["nginx", "-t"])
    if changed:
        run(["systemctl", "reload", "nginx"])
    return changed, backup


def curl_status(url: str, *, method: str = "GET", data_path: Path | None = None, filename: str | None = None, resolve_local: bool = False, timeout: int = 55) -> tuple[int | None, str, str]:
    args = ["curl", "-ksS", "--max-time", str(timeout)]
    if resolve_local:
        args += ["--resolve", "studio.milkcat.org:443:127.0.0.1"]
    if method != "GET":
        args += ["-X", method]
    if filename is not None:
        args += ["-H", f"X-Model2IR-Filename: {filename}"]
    if data_path is not None:
        args += ["-H", "Content-Type: application/octet-stream", "--data-binary", f"@{data_path}"]
    args += ["-w", "\n__STATUS__%{http_code}\n__CTYPE__%{content_type}\n", url]
    proc = run(args, check=False, timeout=timeout + 5)
    text = proc.stdout
    if "\n__STATUS__" not in text:
        return None, "", text
    body, tail = text.rsplit("\n__STATUS__", 1)
    status_text, _, ctype_tail = tail.partition("\n__CTYPE__")
    try:
        code = int(status_text.strip())
    except ValueError:
        code = None
    return code, ctype_tail.strip(), body


def wait_json_health(url: str, *, resolve_local: bool = False, attempts: int = 30) -> dict:
    last = (None, "", "")
    for _ in range(attempts):
        last = curl_status(url, resolve_local=resolve_local, timeout=8)
        if last[0] == 200 and "json" in last[1]:
            try:
                payload = json.loads(last[2])
            except json.JSONDecodeError:
                payload = None
            if isinstance(payload, dict) and payload.get("ok") is True:
                return payload
        time.sleep(1)
    raise RuntimeError(f"health check failed status={last[0]} content_type={last[1]!r}")


def make_minimal_glb(path: Path) -> None:
    doc = json.dumps({"asset": {"version": "2.0"}, "nodes": [], "meshes": []}, separators=(",", ":")).encode()
    doc += b" " * ((4 - len(doc) % 4) % 4)
    chunk = struct.pack("<II", len(doc), 0x4E4F534A) + doc
    path.write_bytes(struct.pack("<4sII", b"glTF", 2, 12 + len(chunk)) + chunk)


def validate_sources(root: Path) -> dict[str, Path]:
    sources = {
        "server": root / "scripts/model2ir_lab_server.py",
        "package": root / "libs/model2ir/src/model2ir",
        "page": root / "web_assets/model2ir-lab.html",
    }
    if not sources["server"].is_file() or not sources["package"].is_dir() or not sources["page"].is_file():
        raise RuntimeError("staged Model2IR Lab source set is incomplete")
    page = sources["page"].read_text(encoding="utf-8")
    required = [
        'data-model2ir-lab-version="0.1.0"',
        "/api/model2ir/v1/analyze",
        "Three.js 在這裡只負責顯示模型",
        "multi-file",
        "stabilized-candidate",
    ]
    missing = [x for x in required if x not in page]
    if missing:
        raise RuntimeError(f"Model2IR Lab page identity incomplete: missing_count={len(missing)}")
    return sources


def install_release(root: Path, source_sha: str) -> tuple[Path, str | None]:
    sources = validate_sources(root)
    release = RUNTIME_ROOT / "releases" / source_sha
    previous = None
    if CURRENT_LINK.is_symlink():
        previous = os.readlink(CURRENT_LINK)
    elif CURRENT_LINK.exists():
        raise RuntimeError("Model2IR Lab current path exists but is not a symlink")

    temp_release = RUNTIME_ROOT / "releases" / f".{source_sha}.tmp-{os.getpid()}"
    shutil.rmtree(temp_release, ignore_errors=True)
    (temp_release / "lib").mkdir(parents=True, exist_ok=True)
    shutil.copy2(sources["server"], temp_release / "model2ir_lab_server.py")
    shutil.copytree(sources["package"], temp_release / "lib/model2ir", dirs_exist_ok=True)
    os.chmod(temp_release / "model2ir_lab_server.py", 0o755)
    for p in temp_release.rglob("*"):
        if p.is_dir():
            os.chmod(p, 0o755)
        elif p.is_file():
            os.chmod(p, 0o644 if p.name != "model2ir_lab_server.py" else 0o755)
    if release.exists():
        shutil.rmtree(release)
    temp_release.rename(release)

    next_link = RUNTIME_ROOT / ".current.next"
    if next_link.exists() or next_link.is_symlink():
        next_link.unlink()
    next_link.symlink_to(release)
    next_link.replace(CURRENT_LINK)
    return release, previous


def restore_current(previous: str | None) -> None:
    if CURRENT_LINK.exists() or CURRENT_LINK.is_symlink():
        CURRENT_LINK.unlink()
    if previous:
        CURRENT_LINK.symlink_to(previous)


def install_static(page: Path) -> tuple[Path | None, bool]:
    STATIC_TARGET.mkdir(parents=True, exist_ok=True)
    target = STATIC_TARGET / "index.html"
    previous = target.read_bytes() if target.is_file() else None
    changed = previous != page.read_bytes()
    if changed:
        fd, tmp_name = tempfile.mkstemp(prefix=".model2ir-lab-", dir=str(STATIC_TARGET))
        os.close(fd)
        tmp = Path(tmp_name)
        try:
            shutil.copy2(page, tmp)
            os.chmod(tmp, 0o644)
            tmp.replace(target)
        finally:
            if tmp.exists():
                tmp.unlink()
    backup = None
    if previous is not None:
        fd, name = tempfile.mkstemp(prefix="model2ir-lab-index-backup-", suffix=".html", dir="/tmp")
        os.close(fd)
        backup = Path(name)
        backup.write_bytes(previous)
    return backup, changed


def restore_static(backup: Path | None) -> None:
    target = STATIC_TARGET / "index.html"
    if backup is None:
        target.unlink(missing_ok=True)
    else:
        shutil.copy2(backup, target)


def main() -> int:
    parser = argparse.ArgumentParser(description="Deploy Model2IR Lab v0.1 onto the governed Oracle Studio boundary")
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--source-sha", required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    source_sha = args.source_sha.lower()
    if not SHA_RE.fullmatch(source_sha):
        raise RuntimeError("source SHA must be exactly 40 lowercase hex characters")
    sources = validate_sources(root)

    RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
    (RUNTIME_ROOT / "releases").mkdir(parents=True, exist_ok=True)
    previous_unit = SYSTEMD_UNIT.read_text(encoding="utf-8") if SYSTEMD_UNIT.is_file() else None
    nginx_original = NGINX_CONFIG.read_text(encoding="utf-8") if NGINX_CONFIG.is_file() else None
    previous_link: str | None = None
    static_backup: Path | None = None
    nginx_backup: Path | None = None
    release: Path | None = None
    static_changed = False
    nginx_changed = False

    try:
        release, previous_link = install_release(root, source_sha)
        SYSTEMD_UNIT.write_text(UNIT, encoding="utf-8")
        os.chmod(SYSTEMD_UNIT, 0o644)
        run(["systemctl", "daemon-reload"])
        run(["systemctl", "enable", SERVICE_NAME])
        run(["systemctl", "restart", SERVICE_NAME])
        local_health = wait_json_health(f"http://127.0.0.1:{SERVICE_PORT}/healthz")
        if local_health.get("model2ir_version") != "0.9.1":
            raise RuntimeError("deployed Model2IR version is not v0.9.1")

        static_backup, static_changed = install_static(sources["page"])
        nginx_changed, nginx_backup = install_nginx_block()
        local_proxy_health = wait_json_health(PUBLIC_BASE + "/api/model2ir/v1/healthz", resolve_local=True, attempts=8)

        with tempfile.TemporaryDirectory(prefix="model2ir-lab-deploy-") as td:
            fixture = Path(td) / "deploy-smoke.glb"
            make_minimal_glb(fixture)
            code, ctype, body = curl_status(
                PUBLIC_BASE + "/api/model2ir/v1/analyze",
                method="POST",
                data_path=fixture,
                filename="deploy-smoke.glb",
                resolve_local=True,
            )
            if code != 200 or "json" not in ctype:
                raise RuntimeError(f"local proxy analyze acceptance failed status={code}")
            payload = json.loads(body)
            analysis = payload.get("analysis") if isinstance(payload, dict) else None
            if not payload.get("ok") or not isinstance(analysis, dict):
                raise RuntimeError("local proxy analyze returned invalid contract")
            if analysis.get("analysis_source") != "python-model2ir-library":
                raise RuntimeError("local proxy analyze did not use Python Model2IR")
            if (analysis.get("summary") or {}).get("inferred", {}).get("result_role") != "stabilized-candidate":
                raise RuntimeError("minimal external GLB was not kept as stabilized-candidate")
            if (analysis.get("truth_policy") or {}).get("automatic_promotion_of_inference") is not False:
                raise RuntimeError("truth promotion guard is not active")

        static_code, static_type, static_body = curl_status(PUBLIC_BASE + "/poc/model2ir-lab/", resolve_local=True, timeout=12)
        if static_code != 200 or "text/html" not in static_type or 'data-model2ir-lab-version="0.1.0"' not in static_body:
            raise RuntimeError("local Studio static Model2IR Lab acceptance failed")

        result = {
            "schema": "model2ir-lab-oracle-deploy/v0.1",
            "ok": True,
            "source_sha": source_sha,
            "release_dir": str(release),
            "runtime_current": str(CURRENT_LINK),
            "service": SERVICE_NAME,
            "service_bind": f"127.0.0.1:{SERVICE_PORT}",
            "model2ir_version": local_health.get("model2ir_version"),
            "static_route": "/poc/model2ir-lab/",
            "api_health_route": "/api/model2ir/v1/healthz",
            "api_analyze_route": "/api/model2ir/v1/analyze",
            "static_changed": static_changed,
            "nginx_changed": nginx_changed,
            "nginx_backup": nginx_backup.name if nginx_backup else None,
            "local_backend_health": bool(local_health.get("ok")),
            "local_proxy_health": bool(local_proxy_health.get("ok")),
            "local_proxy_analysis": True,
            "truth_promotion_guard": True,
            "accepted": [".glb", ".vrm"],
            "multi_file_gltf_supported": False,
            "max_upload_bytes": 32 * 1024 * 1024,
            "uploaded_assets_persisted": False,
            "source_sha256": {
                "server": sha256(sources["server"]),
                "page": sha256(sources["page"]),
            },
        }
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except Exception:
        if nginx_original is not None and NGINX_CONFIG.exists():
            NGINX_CONFIG.write_text(nginx_original, encoding="utf-8")
            run(["nginx", "-t"], check=False)
            run(["systemctl", "reload", "nginx"], check=False)
        if static_backup is not None or static_changed:
            restore_static(static_backup)
        restore_current(previous_link)
        if previous_unit is None:
            SYSTEMD_UNIT.unlink(missing_ok=True)
        else:
            SYSTEMD_UNIT.write_text(previous_unit, encoding="utf-8")
        run(["systemctl", "daemon-reload"], check=False)
        if previous_link:
            run(["systemctl", "restart", SERVICE_NAME], check=False)
        else:
            run(["systemctl", "stop", SERVICE_NAME], check=False)
        raise
    finally:
        if static_backup is not None:
            static_backup.unlink(missing_ok=True)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(
            json.dumps(
                {
                    "schema": "model2ir-lab-oracle-deploy/v0.1",
                    "ok": False,
                    "error_type": type(exc).__name__,
                    "error_length": len(str(exc)),
                    "rolled_back_on_failure": True,
                    "uploaded_assets_persisted": False,
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        raise
