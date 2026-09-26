from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import subprocess
from datetime import datetime, timezone
from typing import Any

SCHEMA = "agentos.bootstrap-request/v1"
RECEIPT_SCHEMA = "agentos.bootstrap-receipt/v1"
ACTION_REPAIR_TRANSPORT = "agentos.transport.repair"
ACTION_DEPLOY_REALM_GATEWAY = "agentos.realm_gateway.deploy"
ACTION_DEPLOY_SOCIAL_RUNTIME = "agentos.social_runtime.deploy"
ACTION_DEPLOY_THREADS_GALAXY = "agentos.threads_galaxy_static.deploy"
ACTION_RECONCILE_CONTROL_INBOX = "agentos.control_inbox.reconcile"
ACTION_PROVISION_ZIWEI_MASTER_REPO = "agentos.repository.provision_ziwei_master"
ACTION_PUBLISH_GALAXY_DAY1 = "agentos.social_threads_galaxy_day1.publish"
ACTION_PUBLISH_MIO_DAY2 = "agentos.social_threads_mio_day2.publish"
ACTION_PUBLISH_MIO_APPROVED = "agentos.social_threads_mio_approved.publish"
ACTION_PUBLISH_SUNLAKE_PERSONA_REPLIES = "agentos.social_threads_sunlake_persona_replies.publish"
ACTION_INSTALL_GALAXY_EXPERIMENT_MONITOR = "agentos.social_threads_experiment_monitor.install"
ACTION_INSPECT_MIO_SQUIRREL = "agentos.social_threads_mio_squirrel.inspect"
ACTION_INSPECT_MIO_RECENT = "agentos.social_threads_mio_recent.inspect"
ACTION_PROBE_MIO_IMAGE_CONTAINER = "agentos.social_threads_mio_image_container.probe"
ACTION_PAUSE_MIO_AUTOREPLY = "agentos.social_threads_mio.pause_autoreply"
ACTION_DEPLOY_MIO_TELEGRAM = "agentos.mio_telegram.deploy"
ALLOWED_ACTIONS = {
    ACTION_REPAIR_TRANSPORT,
    ACTION_DEPLOY_REALM_GATEWAY,
    ACTION_DEPLOY_SOCIAL_RUNTIME,
    ACTION_DEPLOY_THREADS_GALAXY,
    ACTION_RECONCILE_CONTROL_INBOX,
    ACTION_PROVISION_ZIWEI_MASTER_REPO,
    ACTION_PUBLISH_GALAXY_DAY1,
    ACTION_PUBLISH_MIO_DAY2,
    ACTION_PUBLISH_MIO_APPROVED,
    ACTION_PUBLISH_SUNLAKE_PERSONA_REPLIES,
    ACTION_INSTALL_GALAXY_EXPERIMENT_MONITOR,
    ACTION_INSPECT_MIO_SQUIRREL,
    ACTION_INSPECT_MIO_RECENT,
    ACTION_PROBE_MIO_IMAGE_CONTAINER,
    ACTION_PAUSE_MIO_AUTOREPLY,
    ACTION_DEPLOY_MIO_TELEGRAM,
}
MAX_REQUEST_AGE_SECONDS = 900
REQUEST_OWNER = "agentos-node"
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _root() -> Path:
    return Path(os.environ.get("AGENTOS_BOOTSTRAP_ROOT") or "/tmp/agentos-bootstrap-control")


def _ensure(root: Path) -> tuple[Path, Path, Path]:
    requests = root / "requests"
    receipts = root / "receipts"
    rejected = root / "rejected"
    for p in (root, requests, receipts, rejected):
        p.mkdir(parents=True, exist_ok=True)
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


def _validate_request(path: Path, payload: dict[str, Any]) -> tuple[str, str, str | None, str | None]:
    if path.is_symlink():
        raise ValueError("request must not be a symlink")
    if payload.get("schema") != SCHEMA:
        raise ValueError("invalid schema")
    request_id = str(payload.get("request_id") or "").strip()
    action = str(payload.get("action") or "").strip()
    if not request_id or path.name != f"{request_id}.request.json":
        raise ValueError("request_id/path mismatch")
    if action not in ALLOWED_ACTIONS:
        raise ValueError("action is not allowlisted")
    params = payload.get("params") or {}
    if not isinstance(params, dict):
        raise ValueError("params must be an object")
    unknown = set(params) - ({"source_commit", "post_key"} if action == ACTION_PUBLISH_MIO_APPROVED else {"source_commit"})
    post_key = str(params.get("post_key") or "")
    if action == ACTION_PUBLISH_MIO_APPROVED and not re.fullmatch(r"mio-post-[a-z0-9-]{1,72}", post_key):
        raise ValueError("invalid approved Mio post_key")
    if unknown:
        raise ValueError(f"unsupported bootstrap params: {sorted(unknown)}")
    source_commit = str(params.get("source_commit") or "").strip() or None
    if source_commit is not None and not COMMIT_RE.fullmatch(source_commit):
        raise ValueError("source_commit must be an exact lowercase 40-hex commit SHA")
    exact_actions = {
        ACTION_DEPLOY_REALM_GATEWAY,
        ACTION_DEPLOY_SOCIAL_RUNTIME,
        ACTION_DEPLOY_THREADS_GALAXY,
        ACTION_RECONCILE_CONTROL_INBOX,
        ACTION_PROVISION_ZIWEI_MASTER_REPO,
        ACTION_PUBLISH_GALAXY_DAY1,
        ACTION_PUBLISH_SUNLAKE_PERSONA_REPLIES,
        ACTION_INSTALL_GALAXY_EXPERIMENT_MONITOR,
        ACTION_INSPECT_MIO_SQUIRREL,
        ACTION_INSPECT_MIO_RECENT,
        ACTION_PROBE_MIO_IMAGE_CONTAINER,
        ACTION_PAUSE_MIO_AUTOREPLY,
        ACTION_DEPLOY_MIO_TELEGRAM,
    }
    if action in exact_actions and source_commit is None:
        raise ValueError(f"{action} requires exact source_commit")
    created = _parse_time(str(payload.get("created_at") or ""))
    age = (datetime.now(timezone.utc) - created).total_seconds()
    if age < -60 or age > MAX_REQUEST_AGE_SECONDS:
        raise ValueError(f"request outside freshness window: age={age:.1f}s")
    info = path.stat()
    owner = pwd.getpwuid(info.st_uid).pw_name
    if owner != REQUEST_OWNER:
        raise ValueError(f"request owner must be {REQUEST_OWNER}: owner={owner}")
    mode = info.st_mode & 0o777
    if mode & 0o022:
        raise ValueError(f"request must not be group/world-writable: mode={mode:o}")
    authority = payload.get("authority") or {}
    if authority.get("source") != "github-actions" or authority.get("target_user") != "ubuntu":
        raise ValueError("invalid authority envelope")
    if authority.get("arbitrary_shell") is not False:
        raise ValueError("arbitrary shell is forbidden")
    return request_id, action, source_commit, (post_key if action == ACTION_PUBLISH_MIO_APPROVED else None)


def _run_canonical_script(
    script_rel: str,
    *,
    timeout: int,
    source_commit: str | None = None,
    env_extra: dict[str, str] | None = None,
) -> dict[str, Any]:
    repo = Path.home() / "agentmanager"
    tmp = Path("/tmp") / ("agentos-bootstrap-" + Path(script_rel).name)
    steps: list[dict[str, Any]] = []
    source = source_commit or "origin/main"
    fetch_args = ["git", "-C", str(repo), "fetch", "origin", source_commit] if source_commit else ["git", "-C", str(repo), "fetch", "origin", "main"]
    fetch = subprocess.run(fetch_args, text=True, capture_output=True, timeout=60, check=False)
    steps.append({"step": "git_fetch", "source_commit": source_commit, "returncode": fetch.returncode, "stdout": fetch.stdout[-8000:], "stderr": fetch.stderr[-8000:]})
    if fetch.returncode != 0:
        return {"ok": False, "source_commit": source_commit, "steps": steps}
    if source_commit:
        verify = subprocess.run(["git", "-C", str(repo), "cat-file", "-e", f"{source_commit}^{{commit}}"], text=True, capture_output=True, timeout=30, check=False)
        steps.append({"step": "verify_source_commit", "returncode": verify.returncode, "stderr": verify.stderr[-8000:]})
        if verify.returncode != 0:
            return {"ok": False, "source_commit": source_commit, "steps": steps}
    show = subprocess.run(["git", "-C", str(repo), "show", f"{source}:{script_rel}"], text=True, capture_output=True, timeout=30, check=False)
    steps.append({"step": "git_show_script", "source": source, "returncode": show.returncode, "stderr": show.stderr[-8000:]})
    if show.returncode != 0:
        return {"ok": False, "source_commit": source_commit, "steps": steps}
    tmp.write_text(show.stdout, encoding="utf-8")
    os.chmod(tmp, 0o700)
    digest = hashlib.sha256(show.stdout.encode()).hexdigest()
    env = os.environ.copy()
    env["AGENTOS_REPO"] = str(repo)
    if source_commit:
        env["AGENTOS_SOURCE_COMMIT"] = source_commit
    if env_extra:
        env.update(env_extra)
    try:
        run = subprocess.run(["/bin/bash", str(tmp)], text=True, capture_output=True, timeout=timeout, check=False, env=env)
        steps.append({"step": "run_script", "returncode": run.returncode, "stdout": run.stdout[-30000:], "stderr": run.stderr[-20000:]})
        return {"ok": run.returncode == 0, "source_commit": source_commit, "script_sha256": digest, "steps": steps}
    except subprocess.TimeoutExpired as exc:
        steps.append({"step": "run_script", "error": "TimeoutExpired", "timeout": timeout, "stdout": (exc.stdout or "")[-30000:] if isinstance(exc.stdout, str) else "", "stderr": (exc.stderr or "")[-20000:] if isinstance(exc.stderr, str) else ""})
        return {"ok": False, "source_commit": source_commit, "script_sha256": digest, "steps": steps}
    finally:
        tmp.unlink(missing_ok=True)


def _execute(action: str, source_commit: str | None, post_key: str | None = None) -> dict[str, Any]:
    if action == ACTION_REPAIR_TRANSPORT:
        env_extra = {"AGENTOS_ACTION_SPOOL_PREPROVISIONED": "1"}
        if source_commit:
            env_extra["AGENTOS_REF"] = "core/integration"
        return _run_canonical_script("scripts/repair_antigravity_relay_user.sh", timeout=180, source_commit=source_commit, env_extra=env_extra)
    if action == ACTION_RECONCILE_CONTROL_INBOX:
        return _run_canonical_script(
            "scripts/install_control_inbox_bridge_user.sh",
            timeout=180,
            source_commit=source_commit,
            env_extra={"AGENTOS_REF": "core/integration"},
        )
    if action == ACTION_DEPLOY_REALM_GATEWAY:
        return _run_canonical_script("scripts/deploy_realm_gateway_user.sh", timeout=300, source_commit=source_commit)
    if action == ACTION_DEPLOY_SOCIAL_RUNTIME:
        return _run_canonical_script("scripts/deploy_social_runtime_user.sh", timeout=180, source_commit=source_commit)
    if action == ACTION_DEPLOY_THREADS_GALAXY:
        return _run_canonical_script("scripts/deploy_threads_galaxy_static_user.sh", timeout=600, source_commit=source_commit)
    if action == ACTION_PROVISION_ZIWEI_MASTER_REPO:
        return _run_canonical_script("scripts/provision_ziwei_master_repo_user.sh", timeout=120, source_commit=source_commit)
    if action == ACTION_PUBLISH_GALAXY_DAY1:
        return _run_canonical_script("scripts/publish_galaxy_threads_day1_user.sh", timeout=120, source_commit=source_commit)
    if action == ACTION_PROBE_MIO_IMAGE_CONTAINER:
        return _run_canonical_script("scripts/probe_mio_threads_image_container_user.sh", timeout=90, source_commit=source_commit)
    if action == ACTION_PUBLISH_MIO_APPROVED:
        if not post_key:
            raise ValueError("approved post key missing")
        return _run_canonical_script("scripts/publish_galaxy_threads_day1_user.sh", timeout=600, source_commit=source_commit, env_extra={"AGENTOS_SOCIAL_POST_KEY": post_key})
    if action == ACTION_PUBLISH_MIO_DAY2:
        return _run_canonical_script("scripts/publish_galaxy_threads_day1_user.sh", timeout=120, source_commit=source_commit, env_extra={"AGENTOS_SOCIAL_POST_KEY": "mio-second-post-20260919"})
    if action == ACTION_PUBLISH_SUNLAKE_PERSONA_REPLIES:
        return _run_canonical_script("scripts/publish_sunlake_persona_replies_user.sh", timeout=120, source_commit=source_commit)
    if action == ACTION_INSTALL_GALAXY_EXPERIMENT_MONITOR:
        return _run_canonical_script("scripts/install_galaxy_threads_experiment_monitor_user.sh", timeout=120, source_commit=source_commit)
    if action == ACTION_INSPECT_MIO_SQUIRREL:
        return _run_canonical_script("scripts/inspect_mio_squirrel_followup_user.sh", timeout=120, source_commit=source_commit)
    if action == ACTION_INSPECT_MIO_RECENT:
        return _run_canonical_script("scripts/inspect_mio_recent_threads_user.sh", timeout=240, source_commit=source_commit)
    if action == ACTION_PAUSE_MIO_AUTOREPLY:
        return _run_canonical_script("scripts/pause_mio_autoreply_keep_monitor_user.sh", timeout=160, source_commit=source_commit)
    if action == ACTION_DEPLOY_MIO_TELEGRAM:
        return _run_canonical_script("scripts/deploy_mio_telegram_user.sh", timeout=150, source_commit=source_commit)
    raise ValueError("unsupported bootstrap action")


def run_bootstrap_control_plane() -> dict[str, Any] | None:
    """Process at most one fresh fixed-schema bootstrap request as ubuntu.

    Requests may select only a small enumerated action and cannot supply shell,
    paths or executable arguments. Actions that publish runtime code may carry
    only an immutable exact source commit SHA, which is preserved in the receipt.
    """
    requests, receipts, rejected = _ensure(_root())
    candidates = sorted(requests.glob("*.request.json"))
    if not candidates:
        return None
    source = candidates[0]
    started = _now()
    request_id = source.name.removesuffix(".request.json")
    action = "unknown"
    source_commit: str | None = None
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
        request_id, action, source_commit, post_key = _validate_request(source, payload)
        receipt_path = receipts / f"{request_id}.json"
        if receipt_path.exists():
            source.unlink(missing_ok=True)
            return json.loads(receipt_path.read_text(encoding="utf-8"))
        result = _execute(action, source_commit, post_key)
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
            "source_commit": source_commit,
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
