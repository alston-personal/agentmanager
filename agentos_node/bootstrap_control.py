from __future__ import annotations

import fcntl
import hashlib
import json
import os
import tempfile
import time
from pathlib import Path
import pwd
import re
import signal
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
ACTION_PROBE_THREADS_WEB_DM = "agentos.social_threads_web_dm.probe"
ACTION_READ_THREADS_WEB_DM = "agentos.social_threads_web_dm.read"
ACTION_PROBE_THREADS_WEB_DM_LOGIN = "agentos.social_threads_web_dm.login_probe"
ACTION_START_THREADS_WEB_DM_LOGIN = "agentos.social_threads_web_dm.login_start"
ACTION_RUN_MIO_DM_DECISION = "agentos.mio_dm_decision.run"
ACTION_INSTALL_GUI_WORKER = "agentos.gui_worker.install"
ACTION_SMOKE_GUI_WORKER = "agentos.gui_worker.smoke"
ACTION_PROBE_CHATGPT_WEB = "agentos.chatgpt_web.probe"
ACTION_INSTALL_CHATGPT_WEB_BRIDGE = "agentos.chatgpt_web.bridge.install"
ACTION_ACCEPT_CHATGPT_WEB_SESSION = "agentos.chatgpt_web.session.acceptance"
ACTION_PROBE_GEMINI_WEB = "agentos.gemini_web.probe"
ACTION_INSTALL_GEMINI_WEB_BRIDGE = "agentos.gemini_web.bridge.install"
ACTION_ACCEPT_GEMINI_WEB_SESSION = "agentos.gemini_web.session.acceptance"
ACTION_START_GEMINI_WEB_LOGIN = "agentos.gemini_web.login.start"
ACTION_ACCEPT_GEMINI_WEB_ROUNDTRIP = "agentos.gemini_web.roundtrip.acceptance"
ACTION_DEPLOY_MIO_TRYON = "agentos.mio_tryon.deploy"
ACTION_INSTALL_ORACLE_EXEC = "agentos.oracle_exec.install"
ACTION_PROJECT_MIO_OBSERVER = "agentos.mio_observer.project"
ACTION_DEPLOY_STUDIO_WEB_MIO = "agentos.studio_web_mio.deploy"
ACTION_INSTALL_MIO_OBSERVER_TIMER = "agentos.mio_observer.timer.install"
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
    ACTION_PROBE_THREADS_WEB_DM,
    ACTION_READ_THREADS_WEB_DM,
    ACTION_PROBE_THREADS_WEB_DM_LOGIN,
    ACTION_START_THREADS_WEB_DM_LOGIN,
    ACTION_RUN_MIO_DM_DECISION,
    ACTION_INSTALL_GUI_WORKER,
    ACTION_SMOKE_GUI_WORKER,
    ACTION_PROBE_CHATGPT_WEB,
    ACTION_INSTALL_CHATGPT_WEB_BRIDGE,
    ACTION_ACCEPT_CHATGPT_WEB_SESSION,
    ACTION_PROBE_GEMINI_WEB,
    ACTION_INSTALL_GEMINI_WEB_BRIDGE,
    ACTION_ACCEPT_GEMINI_WEB_SESSION,
    ACTION_START_GEMINI_WEB_LOGIN,
    ACTION_ACCEPT_GEMINI_WEB_ROUNDTRIP,
    ACTION_DEPLOY_MIO_TRYON,
    ACTION_INSTALL_ORACLE_EXEC,
    ACTION_PROJECT_MIO_OBSERVER,
    ACTION_DEPLOY_STUDIO_WEB_MIO,
    ACTION_INSTALL_MIO_OBSERVER_TIMER,
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
    if action == ACTION_PUBLISH_MIO_APPROVED:
        allowed_params={"source_commit","post_key"}
    elif action == ACTION_RUN_MIO_DM_DECISION:
        allowed_params={"source_commit","source_run_id","username"}
    elif action == ACTION_DEPLOY_STUDIO_WEB_MIO:
        allowed_params={"source_commit","studio_commit"}
    else:
        allowed_params={"source_commit"}
    unknown = set(params) - allowed_params
    post_key = str(params.get("post_key") or "")
    if action == ACTION_PUBLISH_MIO_APPROVED and not re.fullmatch(r"mio-post-[a-z0-9-]{1,72}", post_key):
        raise ValueError("invalid approved Mio post_key")
    if action == ACTION_RUN_MIO_DM_DECISION:
        source_run_id=str(params.get("source_run_id") or "")
        username=str(params.get("username") or "")
        if not re.fullmatch(r"[0-9]{1,20}",source_run_id):
            raise ValueError("invalid source_run_id")
        if not re.fullmatch(r"[A-Za-z0-9._]{1,64}", username):
            raise ValueError("invalid DM username")
    if action == ACTION_DEPLOY_STUDIO_WEB_MIO:
        studio_commit=str(params.get("studio_commit") or "")
        if not COMMIT_RE.fullmatch(studio_commit):
            raise ValueError("studio_commit must be an exact lowercase 40-hex commit SHA")
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
        ACTION_PROBE_THREADS_WEB_DM,
        ACTION_READ_THREADS_WEB_DM,
        ACTION_PROBE_THREADS_WEB_DM_LOGIN,
        ACTION_START_THREADS_WEB_DM_LOGIN,
        ACTION_RUN_MIO_DM_DECISION,
        ACTION_INSTALL_GUI_WORKER,
        ACTION_SMOKE_GUI_WORKER,
        ACTION_PROBE_CHATGPT_WEB,
        ACTION_INSTALL_CHATGPT_WEB_BRIDGE,
        ACTION_ACCEPT_CHATGPT_WEB_SESSION,
        ACTION_PROBE_GEMINI_WEB,
        ACTION_INSTALL_GEMINI_WEB_BRIDGE,
        ACTION_ACCEPT_GEMINI_WEB_SESSION,
        ACTION_START_GEMINI_WEB_LOGIN,
        ACTION_ACCEPT_GEMINI_WEB_ROUNDTRIP,
        ACTION_DEPLOY_MIO_TRYON,
        ACTION_INSTALL_ORACLE_EXEC,
        ACTION_PROJECT_MIO_OBSERVER,
        ACTION_DEPLOY_STUDIO_WEB_MIO,
        ACTION_INSTALL_MIO_OBSERVER_TIMER,
    }
    if action in exact_actions and source_commit is None:
        raise ValueError(f"{action} requires exact source_commit")
    created = _parse_time(str(payload.get("created_at") or ""))
    age = (datetime.now(timezone.utc) - created).total_seconds()
    if age < -60 or age > MAX_REQUEST_AGE_SECONDS:
        raise ValueError(f"request outside freshness window: age={age:.1f}s")
    info = path.stat()
    owner = pwd.getpwuid(info.st_uid).pw_name
    mode = info.st_mode & 0o777
    if mode & 0o022:
        raise ValueError(f"request must not be group/world-writable: mode={mode:o}")
    authority = payload.get("authority") or {}
    authority_source = str(authority.get("source") or "")
    expected_owner = {
        "github-actions": REQUEST_OWNER,
        "realm-controller": "ubuntu",
    }.get(authority_source)
    if expected_owner is None or authority.get("target_user") != "ubuntu":
        raise ValueError("invalid authority envelope")
    if owner != expected_owner:
        raise ValueError(f"request owner mismatch for {authority_source}: owner={owner}")
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
    fd, tmp_raw = tempfile.mkstemp(prefix="agentos-bootstrap-" + Path(script_rel).name + "-", dir="/tmp")
    os.close(fd)
    tmp = Path(tmp_raw)
    steps: list[dict[str, Any]] = []
    source = source_commit or "origin/main"

    # Exact source commits are normally prefetched by the governed ingress.
    # Avoid concurrent git fetches against the shared live repository when the
    # immutable object is already present.  Missing objects are fetched under a
    # narrow source-materialization lock; execution itself remains parallel.
    local_verify = None
    if source_commit:
        local_verify = subprocess.run(
            ["git", "-C", str(repo), "cat-file", "-e", f"{source_commit}^{{commit}}"],
            text=True, capture_output=True, timeout=30, check=False,
        )
    if source_commit and local_verify is not None and local_verify.returncode == 0:
        steps.append({"step": "git_fetch", "source_commit": source_commit, "returncode": 0, "status": "local_object_present"})
    else:
        lock_path = _root() / "locks" / "oracle-source-materialize.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("a+") as lock_handle:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
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
    proc: subprocess.Popen[str] | None = None
    try:
        proc = subprocess.Popen(
            ["/bin/bash", str(tmp)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            start_new_session=True,
        )
        stdout, stderr = proc.communicate(timeout=timeout)
        steps.append({"step": "run_script", "returncode": proc.returncode, "stdout": stdout[-30000:], "stderr": stderr[-20000:]})
        return {"ok": proc.returncode == 0, "source_commit": source_commit, "script_sha256": digest, "steps": steps}
    except subprocess.TimeoutExpired as exc:
        if proc is not None:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            stdout, stderr = proc.communicate()
        else:
            stdout = exc.stdout or ""
            stderr = exc.stderr or ""
        steps.append({
            "step": "run_script",
            "error": "TimeoutExpired",
            "timeout": timeout,
            "stdout": (stdout or "")[-30000:] if isinstance(stdout, str) else "",
            "stderr": (stderr or "")[-20000:] if isinstance(stderr, str) else "",
        })
        return {"ok": False, "source_commit": source_commit, "script_sha256": digest, "steps": steps}
    finally:
        tmp.unlink(missing_ok=True)


def _execute(action: str, source_commit: str | None, post_key: str | None = None, params: dict[str, Any] | None = None) -> dict[str, Any]:
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
        return _run_canonical_script("scripts/deploy_realm_gateway_user.sh", timeout=600, source_commit=source_commit)
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
    if action == ACTION_PROBE_THREADS_WEB_DM:
        return _run_canonical_script("scripts/probe_threads_web_dm_user.sh", timeout=120, source_commit=source_commit)
    if action == ACTION_READ_THREADS_WEB_DM:
        return _run_canonical_script("scripts/run_threads_web_dm_read_user.sh", timeout=180, source_commit=source_commit)
    if action == ACTION_PROBE_THREADS_WEB_DM_LOGIN:
        return _run_canonical_script("scripts/probe_threads_web_dm_login_user.sh", timeout=120, source_commit=source_commit)
    if action == ACTION_START_THREADS_WEB_DM_LOGIN:
        return _run_canonical_script("scripts/start_threads_web_dm_login_user.sh", timeout=60, source_commit=source_commit)
    if action == ACTION_RUN_MIO_DM_DECISION:
        params=params or {}
        return _run_canonical_script(
            "scripts/run_mio_dm_decision_user.sh",
            timeout=240,
            source_commit=source_commit,
            env_extra={
                "AGENTOS_DM_SOURCE_RUN_ID":str(params.get("source_run_id") or ""),
                "AGENTOS_DM_USERNAME":str(params.get("username") or ""),
            },
        )
    if action == ACTION_INSTALL_GUI_WORKER:
        return _run_canonical_script(
            "scripts/install_oracle_gui_worker_user.sh",
            timeout=1200,
            source_commit=source_commit,
        )
    if action == ACTION_SMOKE_GUI_WORKER:
        return _run_canonical_script(
            "scripts/run_oracle_gui_worker_smoke_user.sh",
            timeout=120,
            source_commit=source_commit,
        )
    if action == ACTION_PROBE_CHATGPT_WEB:
        return _run_canonical_script(
            "scripts/probe_chatgpt_web_user.sh",
            timeout=120,
            source_commit=source_commit,
        )
    if action == ACTION_INSTALL_CHATGPT_WEB_BRIDGE:
        return _run_canonical_script(
            "scripts/install_chatgpt_web_bridge_user.sh",
            timeout=180,
            source_commit=source_commit,
        )
    if action == ACTION_ACCEPT_CHATGPT_WEB_SESSION:
        return _run_canonical_script(
            "scripts/accept_chatgpt_web_session_user.sh",
            timeout=120,
            source_commit=source_commit,
        )
    if action == ACTION_PROBE_GEMINI_WEB:
        return _run_canonical_script(
            "scripts/probe_gemini_web_user.sh",
            timeout=120,
            source_commit=source_commit,
        )
    if action == ACTION_INSTALL_GEMINI_WEB_BRIDGE:
        return _run_canonical_script(
            "scripts/install_gemini_web_bridge_user.sh",
            timeout=180,
            source_commit=source_commit,
        )
    if action == ACTION_ACCEPT_GEMINI_WEB_SESSION:
        return _run_canonical_script(
            "scripts/accept_gemini_web_session_user.sh",
            timeout=120,
            source_commit=source_commit,
        )
    if action == ACTION_START_GEMINI_WEB_LOGIN:
        return _run_canonical_script(
            "scripts/start_gemini_web_login_user.sh",
            timeout=120,
            source_commit=source_commit,
        )
    if action == ACTION_ACCEPT_GEMINI_WEB_ROUNDTRIP:
        return _run_canonical_script(
            "scripts/accept_gemini_web_roundtrip_user.sh",
            timeout=150,
            source_commit=source_commit,
        )
    if action == ACTION_DEPLOY_MIO_TRYON:
        return _run_canonical_script(
            "scripts/deploy_mio_tryon_worker_user.sh",
            timeout=420,
            source_commit=source_commit,
        )
    if action == ACTION_INSTALL_ORACLE_EXEC:
        return _run_canonical_script(
            "scripts/install_thin_client_linux_oracle.sh",
            timeout=420,
            source_commit=source_commit,
        )
    if action == ACTION_PROJECT_MIO_OBSERVER:
        return _run_canonical_script(
            "scripts/project_mio_observer_user.sh",
            timeout=90,
            source_commit=source_commit,
        )
    if action == ACTION_DEPLOY_STUDIO_WEB_MIO:
        params=params or {}
        return _run_canonical_script(
            "scripts/deploy_studio_web_mio_user.sh",
            timeout=600,
            source_commit=source_commit,
            env_extra={"AGENTOS_STUDIO_COMMIT":str(params.get("studio_commit") or "")},
        )
    if action == ACTION_INSTALL_MIO_OBSERVER_TIMER:
        return _run_canonical_script(
            "scripts/install_mio_observer_timer_user.sh",
            timeout=180,
            source_commit=source_commit,
        )
    raise ValueError("unsupported bootstrap action")


def run_bootstrap_control_plane() -> dict[str, Any] | None:
    """Process at most one fresh fixed-schema bootstrap request as ubuntu.

    Requests may select only a small enumerated action and cannot supply shell,
    paths or executable arguments. Actions that publish runtime code may carry
    only an immutable exact source commit SHA, which is preserved in the receipt.
    """
    scheduler_marker = Path(
        os.environ.get("AGENT_DATA_ROOT") or "/home/ubuntu/agent-data"
    ) / "runtime" / "bootstrap-scheduler" / "enabled"
    if scheduler_marker.exists():
        # The role worker pool is the single queue owner when enabled.  Keeping
        # the legacy scheduler-board hook passive prevents double execution.
        return None
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
        result = _execute(action, source_commit, post_key, payload.get("params") or {})
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
