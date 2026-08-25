from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import pwd
import subprocess
from datetime import datetime, timezone
from typing import Any

SCHEMA = "agentos.bootstrap-request/v1"
RECEIPT_SCHEMA = "agentos.bootstrap-receipt/v1"
ACTION_REPAIR_TRANSPORT = "agentos.transport.repair"
MAX_REQUEST_AGE_SECONDS = 900
REQUEST_OWNER = "agentos-node"


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _root() -> Path:
    # Bootstrap transport must not depend on the supplementary `agentos` group:
    # the long-lived ubuntu Chronos process predates that group grant.  Use a
    # deliberately narrow, local-only /tmp rendezvous until Action Relay exists.
    return Path(os.environ.get("AGENTOS_BOOTSTRAP_ROOT") or "/tmp/agentos-bootstrap-control")


def _ensure(root: Path) -> tuple[Path, Path, Path]:
    requests = root / "requests"
    receipts = root / "receipts"
    rejected = root / "rejected"
    for p in (root, requests, receipts, rejected):
        p.mkdir(parents=True, exist_ok=True)
        # Sticky + world traverse/write lets agentos-node submit a fixed-schema
        # request while the ubuntu directory owner retains cleanup authority.
        os.chmod(p, 0o1777)
    return requests, receipts, rejected


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(tmp, 0o644)
    tmp.replace(path)
    os.chmod(path, 0o644)


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _validate_request(path: Path, payload: dict[str, Any]) -> tuple[str, str]:
    if path.is_symlink():
        raise ValueError("request must not be a symlink")
    if payload.get("schema") != SCHEMA:
        raise ValueError("invalid schema")
    request_id = str(payload.get("request_id") or "").strip()
    action = str(payload.get("action") or "").strip()
    if not request_id or path.name != f"{request_id}.request.json":
        raise ValueError("request_id/path mismatch")
    if action != ACTION_REPAIR_TRANSPORT:
        raise ValueError("action is not allowlisted")
    created = _parse_time(str(payload.get("created_at") or ""))
    age = (datetime.now(timezone.utc) - created).total_seconds()
    if age < -60 or age > MAX_REQUEST_AGE_SECONDS:
        raise ValueError(f"request outside freshness window: age={age:.1f}s")
    stat = path.stat()
    owner = pwd.getpwuid(stat.st_uid).pw_name
    if owner != REQUEST_OWNER:
        raise ValueError(f"request owner must be {REQUEST_OWNER}: owner={owner}")
    mode = stat.st_mode & 0o777
    if mode & 0o022:
        raise ValueError(f"request must not be group/world-writable: mode={mode:o}")
    authority = payload.get("authority") or {}
    if authority.get("source") != "github-actions" or authority.get("target_user") != "ubuntu":
        raise ValueError("invalid authority envelope")
    if authority.get("arbitrary_shell") is not False:
        raise ValueError("arbitrary shell is forbidden")
    return request_id, action


def _run_repair() -> dict[str, Any]:
    repo = Path.home() / "agentmanager"
    tmp = Path("/tmp/agentos-bootstrap-control-repair.sh")
    steps: list[dict[str, Any]] = []

    fetch = subprocess.run(
        ["git", "-C", str(repo), "fetch", "origin", "main"],
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )
    steps.append({"step": "git_fetch", "returncode": fetch.returncode, "stdout": fetch.stdout[-8000:], "stderr": fetch.stderr[-8000:]})
    if fetch.returncode != 0:
        return {"ok": False, "steps": steps}

    show = subprocess.run(
        ["git", "-C", str(repo), "show", "origin/main:scripts/repair_antigravity_relay_user.sh"],
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    steps.append({"step": "git_show_repair", "returncode": show.returncode, "stderr": show.stderr[-8000:]})
    if show.returncode != 0:
        return {"ok": False, "steps": steps}

    tmp.write_text(show.stdout, encoding="utf-8")
    os.chmod(tmp, 0o700)
    digest = hashlib.sha256(show.stdout.encode()).hexdigest()

    env = os.environ.copy()
    env["AGENTOS_REPO"] = str(repo)
    env["AGENTOS_ACTION_SPOOL_PREPROVISIONED"] = "1"
    try:
        repair = subprocess.run(
            ["/bin/bash", str(tmp)],
            text=True,
            capture_output=True,
            timeout=180,
            check=False,
            env=env,
        )
        steps.append({
            "step": "repair_transport",
            "returncode": repair.returncode,
            "stdout": repair.stdout[-30000:],
            "stderr": repair.stderr[-20000:],
        })
        return {"ok": repair.returncode == 0, "repair_sha256": digest, "steps": steps}
    except subprocess.TimeoutExpired as exc:
        steps.append({"step": "repair_transport", "error": "TimeoutExpired", "timeout": 180, "stdout": (exc.stdout or "")[-30000:] if isinstance(exc.stdout, str) else "", "stderr": (exc.stderr or "")[-20000:] if isinstance(exc.stderr, str) else ""})
        return {"ok": False, "repair_sha256": digest, "steps": steps}
    finally:
        tmp.unlink(missing_ok=True)


def run_bootstrap_control_plane() -> dict[str, Any] | None:
    """Process at most one fresh, allowlisted request under the ubuntu Chronos identity.

    This is deterministic and transitional: request data cannot supply shell text,
    only the fixed transport-repair action is accepted, and the /tmp rendezvous is
    expected to be retired after Action Relay has been established.
    """
    root = _root()
    requests, receipts, rejected = _ensure(root)
    candidates = sorted(requests.glob("*.request.json"))
    if not candidates:
        return None

    source = candidates[0]
    started = _now()
    request_id = source.name.removesuffix(".request.json")
    action = "unknown"
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
        request_id, action = _validate_request(source, payload)
        receipt_path = receipts / f"{request_id}.json"
        if receipt_path.exists():
            source.unlink(missing_ok=True)
            return json.loads(receipt_path.read_text(encoding="utf-8"))

        result = _run_repair()
        receipt: dict[str, Any] = {
            "schema": RECEIPT_SCHEMA,
            "request_id": request_id,
            "action": action,
            "executor_user": os.environ.get("USER") or str(os.getuid()),
            "executor_uid": os.getuid(),
            "started_at": started,
            "completed_at": _now(),
            **result,
        }
        _atomic_json(receipt_path, receipt)
        source.unlink(missing_ok=True)
        return receipt
    except BaseException as exc:
        receipt = {
            "schema": RECEIPT_SCHEMA,
            "request_id": request_id,
            "action": action,
            "executor_user": os.environ.get("USER") or str(os.getuid()),
            "executor_uid": os.getuid(),
            "started_at": started,
            "completed_at": _now(),
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
        }
        try:
            _atomic_json(receipts / f"{request_id}.json", receipt)
        finally:
            try:
                source.replace(rejected / source.name)
            except OSError:
                pass
        return receipt
