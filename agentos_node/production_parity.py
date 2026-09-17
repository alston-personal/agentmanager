"""Node-authoritative production parity inspection.

Production truth is observed from the runtime node itself. Callers such as
ChatGPT must consume the emitted receipt rather than substituting their own
sandbox DNS/HTTP observations.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
import json
import socket
import subprocess
import urllib.error
import urllib.request


RECEIPT_SCHEMA = "agentos.execution-receipt/v1"
CAPABILITY = "leopardcat.production.parity.inspect"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _run(argv: list[str], *, cwd: str | None = None, timeout: float = 8.0) -> dict[str, Any]:
    try:
        p = subprocess.run(argv, cwd=cwd, text=True, capture_output=True, timeout=timeout, check=False)
        return {"ok": p.returncode == 0, "returncode": p.returncode, "stdout": p.stdout.strip(), "stderr": p.stderr.strip()}
    except Exception as exc:
        return {"ok": False, "error": type(exc).__name__, "detail": str(exc)}


def _http_probe(url: str, *, timeout: float = 8.0) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return {"ok": 200 <= response.status < 500, "status": response.status, "url": url}
    except urllib.error.HTTPError as exc:
        return {"ok": exc.code < 500, "status": exc.code, "url": url, "error": "http_error"}
    except urllib.error.URLError as exc:
        reason = exc.reason
        if isinstance(reason, socket.gaierror):
            kind = "dns_error"
        else:
            kind = "transport_error"
        return {"ok": False, "url": url, "error": kind, "detail": str(reason)}
    except socket.gaierror as exc:
        return {"ok": False, "url": url, "error": "dns_error", "detail": str(exc)}
    except Exception as exc:
        return {"ok": False, "url": url, "error": type(exc).__name__, "detail": str(exc)}


def inspect_request(
    request: dict[str, Any],
    *,
    runner: Callable[..., dict[str, Any]] = _run,
    http_probe: Callable[..., dict[str, Any]] = _http_probe,
) -> dict[str, Any]:
    if request.get("schema") != "agentos.execution-request/v1":
        raise ValueError("unsupported execution request schema")
    if request.get("capability") != CAPABILITY:
        raise ValueError(f"unsupported capability: {request.get('capability')}")

    params = dict(request.get("parameters") or {})
    repo_path = str(params.get("repo_path") or "/home/ubuntu/leopardcat-tarot")
    service = str(params.get("service") or "leopardcat-tarot.service")
    port = int(params.get("listen_port") or 8088)
    public_url = str(params.get("public_url") or "https://leopardcat-tarot.milkcat.org")
    health_path = str(params.get("health_path") or "/api/stats")
    expected_sha = str(request.get("source_sha") or "")

    git = runner(["git", "rev-parse", "HEAD"], cwd=repo_path)
    branch = runner(["git", "branch", "--show-current"], cwd=repo_path)
    service_state = runner(["systemctl", "is-active", service])
    local = http_probe(f"http://127.0.0.1:{port}{health_path}")
    public = http_probe(f"{public_url.rstrip('/')}{health_path}")

    observed_sha = str(git.get("stdout") or "") if git.get("ok") else ""
    sha_match = bool(expected_sha and observed_sha and expected_sha == observed_sha)
    service_active = bool(service_state.get("ok") and service_state.get("stdout") == "active")
    runtime_available = service_active and bool(local.get("ok"))
    public_available = bool(public.get("ok"))

    if sha_match and runtime_available and public_available:
        parity = "matched"
    elif not observed_sha or not runtime_available or public.get("error") in {"dns_error", "transport_error"}:
        parity = "unavailable"
    else:
        parity = "mismatch"

    return {
        "schema": RECEIPT_SCHEMA,
        "request_id": request.get("request_id"),
        "project_id": request.get("project_id"),
        "capability": CAPABILITY,
        "environment": request.get("environment") or "production",
        "status": "completed",
        "parity": parity,
        "expected": {"source_ref": request.get("source_ref"), "source_sha": expected_sha},
        "observed": {
            "repo_path": repo_path,
            "git_sha": observed_sha or None,
            "git_branch": branch.get("stdout") if branch.get("ok") else None,
            "service": {"name": service, "active": service_active, "evidence": service_state},
            "local_probe": local,
            "public_probe": public,
        },
        "authority": {
            "kind": "runtime_node",
            "rule": "oracle_runtime_receipt_over_chat_sandbox_probe",
            "sandbox_fallback_allowed": False,
        },
        "checked_at": _now(),
    }


def inspect_file(request_path: str, output_path: str | None = None) -> dict[str, Any]:
    request = json.loads(Path(request_path).read_text(encoding="utf-8"))
    receipt = inspect_request(request)
    if output_path:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return receipt
