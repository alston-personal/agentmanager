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
import shlex
import subprocess
from datetime import datetime, timezone
from typing import Any

SCHEMA = "agentos.bootstrap-request/v1"
RECEIPT_SCHEMA = "agentos.bootstrap-receipt/v1"
ACTION_REPAIR_TRANSPORT = "agentos.transport.repair"
ACTION_RUNNER_WINDOW_PROBE = "agentos.runner_window.probe"
ACTION_RELAY_STATUS = "agentos.relay.status"
ACTION_SCHEDULER_STATUS = "agentos.scheduler.status"
ACTION_RELAY_RESTART = "agentos.relay.restart"
ACTION_NODE_TRANSACTIONAL_OTA = "agentos.node.transactional_ota"
ACTION_REALM_NODE_INSPECT = "agentos.realm_node.inspect"
ACTION_REALM_DESKTOP_PROBE = "agentos.realm_desktop.probe"
ACTION_REALM_EXECUTOR_RECONCILE = "agentos.realm_executor.reconcile"
ACTION_GOOGLE_FLOW_GENERATE = "agentos.google_flow.generate"
ACTION_GOOGLE_VIDS_GENERATE = "agentos.google_vids.generate"
ACTION_DEPLOY_REALM_GATEWAY = "agentos.realm_gateway.deploy"
ACTION_DEPLOY_SOCIAL_RUNTIME = "agentos.social_runtime.deploy"
ACTION_RECONCILE_CONTENT_SOCIAL = "agentos.content_social.reconcile"
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
ACTION_ACTIVATE_OURSONG_PERSONA = "agentos.oursong_persona.activate"
ACTION_PROBE_OURSONG_PERSONA = "agentos.oursong_persona.status"
ACTION_PROBE_PERSONA_PDCA_RUNTIME = "agentos.persona_pdca_runtime.probe"
ACTION_EXECUTOR_JOB_SUBMIT = "agentos.executor_job.submit"
ACTION_EXECUTOR_JOB_INSPECT = "agentos.executor_job.inspect"
ALLOWED_ACTIONS = {
    ACTION_REPAIR_TRANSPORT,
    ACTION_RUNNER_WINDOW_PROBE,
    ACTION_RELAY_STATUS,
    ACTION_SCHEDULER_STATUS,
    ACTION_RELAY_RESTART,
    ACTION_NODE_TRANSACTIONAL_OTA,
    ACTION_REALM_NODE_INSPECT,
    ACTION_REALM_DESKTOP_PROBE,
    ACTION_REALM_EXECUTOR_RECONCILE,
    ACTION_GOOGLE_FLOW_GENERATE,
    ACTION_GOOGLE_VIDS_GENERATE,
    ACTION_DEPLOY_REALM_GATEWAY,
    ACTION_DEPLOY_SOCIAL_RUNTIME,
    ACTION_RECONCILE_CONTENT_SOCIAL,
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
    ACTION_ACTIVATE_OURSONG_PERSONA,
    ACTION_PROBE_OURSONG_PERSONA,
    ACTION_PROBE_PERSONA_PDCA_RUNTIME,
    ACTION_EXECUTOR_JOB_SUBMIT,
    ACTION_EXECUTOR_JOB_INSPECT,
}
MAX_REQUEST_AGE_SECONDS = 900
RELAY_STALE_PROCESSING_SECONDS = 600
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
    elif action == ACTION_RECONCILE_CONTENT_SOCIAL:
        allowed_params={"source_commit","account_ref"}
    elif action == ACTION_NODE_TRANSACTIONAL_OTA:
        allowed_params={"source_commit","node_id","candidate_commit"}
    elif action in {ACTION_REALM_NODE_INSPECT, ACTION_REALM_DESKTOP_PROBE, ACTION_REALM_EXECUTOR_RECONCILE}:
        allowed_params={"source_commit","node_id"}
    elif action in {ACTION_GOOGLE_FLOW_GENERATE, ACTION_GOOGLE_VIDS_GENERATE}:
        allowed_params={"source_commit","prompt"}
    elif action == ACTION_EXECUTOR_JOB_SUBMIT:
        allowed_params={"source_commit","job_type"}
    elif action == ACTION_EXECUTOR_JOB_INSPECT:
        allowed_params={"source_commit","job_id"}
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
    if action == ACTION_RECONCILE_CONTENT_SOCIAL:
        account_ref=str(params.get("account_ref") or "")
        if not re.fullmatch(r"[A-Za-z0-9._-]{1,80}", account_ref):
            raise ValueError("invalid content social account_ref")
    if action == ACTION_NODE_TRANSACTIONAL_OTA:
        node_id=str(params.get("node_id") or "")
        candidate_commit=str(params.get("candidate_commit") or "")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", node_id):
            raise ValueError("invalid OTA node_id")
        if not COMMIT_RE.fullmatch(candidate_commit):
            raise ValueError("candidate_commit must be an exact lowercase 40-hex commit SHA")
    if action in {ACTION_REALM_NODE_INSPECT, ACTION_REALM_DESKTOP_PROBE, ACTION_REALM_EXECUTOR_RECONCILE}:
        node_id=str(params.get("node_id") or "")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", node_id):
            raise ValueError("invalid Realm node_id")
    if action in {ACTION_GOOGLE_FLOW_GENERATE, ACTION_GOOGLE_VIDS_GENERATE}:
        prompt=str(params.get("prompt") or "")
        if not (1 <= len(prompt) <= 1600):
            raise ValueError("invalid Google media prompt length")
        if "\x00" in prompt:
            raise ValueError("invalid Google media prompt")
    if action == ACTION_EXECUTOR_JOB_SUBMIT:
        job_type=str(params.get("job_type") or "")
        from agent_core.executor_job_contract import canonical_executor_job_request
        canonical_executor_job_request(job_type)
    if action == ACTION_EXECUTOR_JOB_INSPECT:
        job_id=str(params.get("job_id") or "")
        from agent_core.executor_job_contract import validate_executor_job_id
        validate_executor_job_id(job_id)
    if unknown:
        raise ValueError(f"unsupported bootstrap params: {sorted(unknown)}")
    source_commit = str(params.get("source_commit") or "").strip() or None
    if source_commit is not None and not COMMIT_RE.fullmatch(source_commit):
        raise ValueError("source_commit must be an exact lowercase 40-hex commit SHA")
    exact_actions = {
        ACTION_NODE_TRANSACTIONAL_OTA,
        ACTION_DEPLOY_REALM_GATEWAY,
        ACTION_DEPLOY_SOCIAL_RUNTIME,
        ACTION_RECONCILE_CONTENT_SOCIAL,
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
        ACTION_ACTIVATE_OURSONG_PERSONA,
        ACTION_PROBE_OURSONG_PERSONA,
        ACTION_PROBE_PERSONA_PDCA_RUNTIME,
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


def _restart_antigravity_relay() -> dict[str, Any]:
    from agentos_node.action_relay import ActionRelayClient

    # Reconcile stale processing through a narrow group-boundary helper before
    # restart. The scheduler itself keeps its normal user context; only this
    # fixed, non-replay quarantine operation enters the shared agentos group.
    relay_root = Path(os.environ.get("AGENT_DATA_ROOT") or "/home/ubuntu/agent-data") / "runtime" / "antigravity-relay"
    runtime_root = Path(__file__).resolve().parents[1]
    reconcile_cmd = " ".join([
        "/usr/bin/env",
        "PYTHONPATH=" + shlex.quote(str(runtime_root)),
        "/usr/bin/python3",
        "-m",
        "agentos_node.antigravity_relay_worker",
        "--root",
        shlex.quote(str(relay_root)),
        "--reconcile-only",
    ])
    stop = subprocess.run(
        ["systemctl", "--user", "stop", "agentos-antigravity-relay.service"],
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )
    if stop.returncode != 0:
        raise RuntimeError("relay stop before stale quarantine failed")

    reconcile = subprocess.run(
        ["/usr/bin/sg", "agentos", "-c", reconcile_cmd],
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
        cwd=str(runtime_root),
    )
    if reconcile.returncode != 0:
        stderr = str(reconcile.stderr or "").casefold()
        stdout = str(reconcile.stdout or "").casefold()
        combined = stderr + "\n" + stdout
        if "permission denied" in combined:
            failure = "permission_denied"
        elif "invalid group" in combined or "does not exist" in combined and "group" in combined:
            failure = "group_entry_failed"
        elif "no such file or directory" in combined:
            failure = "invalid_spool"
        else:
            failure = "unexpected"
        raise RuntimeError(
            f"relay stale quarantine helper failed rc={reconcile.returncode} class={failure}"
        )
    try:
        reconcile_payload = json.loads(reconcile.stdout or "{}")
        quarantined = int(reconcile_payload.get("reconciled") or 0)
    except Exception as exc:
        raise RuntimeError("relay stale quarantine helper returned invalid result") from exc

    client = ActionRelayClient("/home/ubuntu/agent-data/runtime/action-relay")
    capsule = client.submit("agentos.antigravity.restart", {"service": "agentos-antigravity-relay"})
    capsule_id = str(capsule.get("capsule_id") or "")
    deadline = time.monotonic() + 60.0
    receipt = None
    while time.monotonic() < deadline:
        receipt = client.receipt(capsule_id)
        if receipt is not None:
            break
        time.sleep(0.5)
    ok = bool(receipt and receipt.get("ok") is True and receipt.get("service") == "agentos-antigravity-relay.service")
    markers = [
        "relay_restart_service=agentos-antigravity-relay.service",
        f"relay_restart_quarantined_stale={quarantined}",
        "relay_restart=" + ("PASS" if ok else "FAIL"),
    ]
    return {
        "ok": ok,
        "source_commit": None,
        "steps": [{
            "step": "relay_restart",
            "returncode": 0 if ok else 1,
            "stdout": "\n".join(markers) + "\n",
            "stderr": "",
        }],
    }


def _scheduler_status_probe() -> dict[str, Any]:
    root = _root()
    requests, receipts, rejected = _ensure(root)
    now = time.time()
    pending = [p for p in requests.glob("*.request.json") if p.is_file()]
    ages = [max(0, int(now - p.stat().st_mtime)) for p in pending]
    oldest = max(ages) if ages else 0
    stalled = sum(1 for age in ages if age > MAX_REQUEST_AGE_SECONDS)
    markers = [
        f"scheduler_status_pending_count={len(pending)}",
        f"scheduler_status_pending_oldest_seconds={oldest}",
        f"scheduler_status_stalled_count={stalled}",
        f"scheduler_status_receipts_count={sum(1 for p in receipts.glob('*.json') if p.is_file())}",
        f"scheduler_status_rejected_count={sum(1 for p in rejected.glob('*.json') if p.is_file())}",
        "scheduler_status=PASS",
    ]
    return {
        "ok": True,
        "source_commit": None,
        "steps": [{"step": "scheduler_status", "returncode": 0, "stdout": "\n".join(markers) + "\n", "stderr": ""}],
    }


def _relay_status() -> dict[str, Any]:
    root = Path(os.environ.get("AGENT_DATA_ROOT") or "/home/ubuntu/agent-data") / "runtime" / "antigravity-relay"
    now = time.time()

    def count_and_oldest(name: str) -> tuple[int, int]:
        path = root / name
        files = [p for p in path.glob("relay-*.json") if p.is_file()] if path.is_dir() else []
        ages = [max(0, int(now - p.stat().st_mtime)) for p in files]
        return len(files), max(ages) if ages else 0

    inbox_count, inbox_oldest = count_and_oldest("inbox")
    processing_count, processing_oldest = count_and_oldest("processing")
    receipts_count, _ = count_and_oldest("receipts")

    def active(unit: str) -> str:
        proc = subprocess.run(
            ["systemctl", "--user", "is-active", unit],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        value = (proc.stdout or "").strip()
        return value if value in {"active", "inactive", "failed", "activating", "deactivating"} else "unknown"

    antigravity = active("agentos-antigravity-relay.service")
    action_relay = active("agentos-action-relay.service")
    stale_processing = processing_count > 0 and processing_oldest >= RELAY_STALE_PROCESSING_SECONDS
    healthy = antigravity == "active" and action_relay == "active" and not stale_processing
    markers = [
        f"relay_status_antigravity_service={antigravity}",
        f"relay_status_action_service={action_relay}",
        f"relay_status_inbox_count={inbox_count}",
        f"relay_status_processing_count={processing_count}",
        f"relay_status_receipts_count={receipts_count}",
        f"relay_status_inbox_oldest_seconds={inbox_oldest}",
        f"relay_status_processing_oldest_seconds={processing_oldest}",
        "relay_status_stale_processing=" + ("YES" if stale_processing else "NO"),
        "relay_status=" + ("PASS" if healthy else "FAIL"),
    ]
    return {
        "ok": True,
        "source_commit": None,
        "steps": [{"step": "relay_status", "returncode": 0, "stdout": "\n".join(markers) + "\n", "stderr": ""}],
    }



def _realm_node_inspect(node_id: str) -> dict[str, Any]:
    from agent_core.node_registry import NodeRegistry

    nodes = NodeRegistry().node_map().get("nodes") or []
    node = next((item for item in nodes if str(item.get("node_id") or "") == node_id), None)
    if node is None:
        markers = [
            f"realm_node_id={node_id}",
            "realm_node_status=NOT_REGISTERED",
            "realm_node_status_reason=node_not_registered",
            "realm_node_heartbeat_age_seconds=unknown",
            "realm_node_desktop_capable=NO",
            "realm_node_inspect=NOT_REGISTERED",
        ]
        return {
            "ok": True,
            "steps": [{"step": "realm_node_inspect", "returncode": 0, "stdout": "\n".join(markers) + "\n", "stderr": ""}],
        }

    caps = set(node.get("capabilities") or [])
    heartbeat_age = node.get("heartbeat_age_seconds")
    runtime = node.get("runtime") if isinstance(node.get("runtime"), dict) else {}
    runtime_status = str(runtime.get("status") or "unknown")
    runtime_commit = str(runtime.get("source_commit") or "")
    if runtime_commit and not re.fullmatch(r"[0-9a-f]{40}", runtime_commit):
        runtime_commit = "invalid"
    markers = [
        f"realm_node_id={node_id}",
        "realm_node_status=" + str(node.get("status") or "unknown"),
        "realm_node_status_reason=" + str(node.get("status_reason") or ""),
        "realm_node_heartbeat_age_seconds=" + (str(int(heartbeat_age)) if isinstance(heartbeat_age, (int, float)) else "unknown"),
        "realm_node_platform=" + str(node.get("platform") or ""),
        "realm_node_role=" + str(node.get("role") or ""),
        "realm_node_capability_count=" + str(len(caps)),
        "realm_node_desktop_capable=" + ("YES" if "desktop.session.inspect" in caps else "NO"),
        "realm_node_runtime_status=" + runtime_status,
        "realm_node_runtime_source_commit=" + runtime_commit,
        "realm_node_inspect=PASS",
    ]
    return {
        "ok": True,
        "steps": [{"step": "realm_node_inspect", "returncode": 0, "stdout": "\n".join(markers) + "\n", "stderr": ""}],
    }


def _realm_desktop_probe(node_id: str) -> dict[str, Any]:
    from agent_core.node_registry import NodeRegistry
    from agent_core.realm_fabric import RealmFabricStore

    nodes = NodeRegistry().node_map().get("nodes") or []
    node = next((item for item in nodes if str(item.get("node_id") or "") == node_id), None)
    if node is None:
        classification = "NOT_REGISTERED"
    elif str(node.get("status") or "") != "online":
        classification = "OFFLINE"
    elif "desktop.session.inspect" not in set(node.get("capabilities") or []):
        classification = "CAPABILITY_MISSING"
    else:
        task_id = "runner-window-desktop-probe-" + node_id + "-" + str(int(time.time()))
        fabric = RealmFabricStore()
        fabric.queue_task(node_id, {
            "schema": "agentos.node-task/v0.1",
            "task_id": task_id,
            "action": "desktop.session.inspect",
            "cognition_ids_used": [],
        })
        deadline = time.monotonic() + 45
        receipt = None
        while time.monotonic() < deadline:
            receipt = fabric.get_receipt(task_id)
            if receipt is not None:
                break
            time.sleep(1)
        if receipt is None:
            classification = "TIMEOUT"
        elif receipt.get("ok") is not True:
            classification = "ERROR"
        elif bool((receipt.get("desktop") or {}).get("interactive")):
            classification = "READY"
        else:
            classification = "NOT_INTERACTIVE"

    markers = [
        f"realm_desktop_node_id={node_id}",
        f"realm_desktop_probe={classification}",
    ]
    return {
        "ok": True,
        "steps": [{"step": "realm_desktop_probe", "returncode": 0, "stdout": "\n".join(markers) + "\n", "stderr": ""}],
    }



def _realm_executor_reconcile(node_id: str) -> dict[str, Any]:
    from agent_core.node_registry import NodeRegistry
    from agent_core.realm_fabric import RealmFabricStore

    nodes = NodeRegistry().node_map().get("nodes") or []
    node = next((item for item in nodes if str(item.get("node_id") or "") == node_id), None)
    classification = "UNKNOWN"
    executor_rows: list[dict[str, Any]] = []
    if node is None:
        classification = "NOT_REGISTERED"
    elif str(node.get("status") or "") != "online":
        classification = "OFFLINE"
    elif "agent.executor.reconcile" not in set(node.get("capabilities") or []):
        classification = "CAPABILITY_MISSING"
    else:
        task_id = "runner-window-executor-reconcile-" + node_id + "-" + str(int(time.time()))
        fabric = RealmFabricStore()
        fabric.queue_task(node_id, {
            "schema": "agentos.node-task/v0.1",
            "task_id": task_id,
            "action": "agent.executor.reconcile",
            "cognition_ids_used": [],
        })
        deadline = time.monotonic() + 150
        receipt = None
        while time.monotonic() < deadline:
            receipt = fabric.get_receipt(task_id)
            if receipt is not None:
                break
            time.sleep(1)
        if receipt is None:
            classification = "TIMEOUT"
        elif receipt.get("ok") is not True:
            classification = "ERROR"
        else:
            adoption = receipt.get("executor_adoption") or {}
            raw_rows = adoption.get("executors") or []
            for raw in raw_rows:
                if not isinstance(raw, dict):
                    continue
                executor_id = str(raw.get("executor_id") or "")
                if executor_id not in {"codex", "gemini", "claude-code"}:
                    continue
                executor_rows.append({
                    "executor_id": executor_id,
                    "state": str(raw.get("state") or "UNKNOWN"),
                    "classification": str((raw.get("provider_health") or {}).get("classification") or ""),
                    "stable_routable": raw.get("stable_routable") is True,
                })
            by_id = {row["executor_id"]: row for row in executor_rows}
            states = [by_id.get(name, {}).get("state", "MISSING") for name in ("codex", "gemini", "claude-code")]
            stable = [bool(by_id.get(name, {}).get("stable_routable")) for name in ("codex", "gemini", "claude-code")]
            if all(state == "READY" for state in states) and all(stable):
                classification = "READY"
            elif all(state == "READY" for state in states):
                classification = "READY_WARMING"
            elif any(state == "AUTH_REQUIRED" for state in states):
                classification = "AUTH_REQUIRED"
            elif any(state == "READY" for state in states):
                classification = "PARTIAL"
            else:
                classification = "UNAVAILABLE"

    by_id = {row["executor_id"]: row for row in executor_rows}
    markers = [
        f"realm_executor_node_id={node_id}",
        f"realm_executor_reconcile={classification}",
    ]
    for executor_id in ("codex", "gemini", "claude-code"):
        safe_id = executor_id.replace("-", "_")
        row = by_id.get(executor_id) or {}
        markers.extend([
            f"realm_executor_{safe_id}_state={row.get('state', 'UNKNOWN')}",
            f"realm_executor_{safe_id}_classification={row.get('classification', '')}",
            f"realm_executor_{safe_id}_stable_routable={str(bool(row.get('stable_routable'))).lower()}",
        ])
    return {
        "ok": True,
        "steps": [{"step": "realm_executor_reconcile", "returncode": 0, "stdout": "\n".join(markers) + "\n", "stderr": ""}],
    }

def _execute(action: str, source_commit: str | None, post_key: str | None = None, params: dict[str, Any] | None = None) -> dict[str, Any]:
    if action == ACTION_RUNNER_WINDOW_PROBE:
        return {
            "ok": True,
            "source_commit": source_commit,
            "steps": [{"step": "runner_window_probe", "returncode": 0, "stdout": "runner_window_probe=PASS\n", "stderr": ""}],
        }
    if action == ACTION_RELAY_STATUS:
        result = _relay_status()
        result["source_commit"] = source_commit
        return result
    if action == ACTION_SCHEDULER_STATUS:
        result = _scheduler_status_probe()
        result["source_commit"] = source_commit
        return result
    if action == ACTION_RELAY_RESTART:
        result = _restart_antigravity_relay()
        result["source_commit"] = source_commit
        return result
    if action == ACTION_REALM_NODE_INSPECT:
        params = params or {}
        result = _realm_node_inspect(str(params.get("node_id") or ""))
        result["source_commit"] = source_commit
        return result
    if action == ACTION_REALM_DESKTOP_PROBE:
        params = params or {}
        result = _realm_desktop_probe(str(params.get("node_id") or ""))
        result["source_commit"] = source_commit
        return result
    if action == ACTION_REALM_EXECUTOR_RECONCILE:
        params = params or {}
        result = _realm_executor_reconcile(str(params.get("node_id") or ""))
        result["source_commit"] = source_commit
        return result
    if action == ACTION_GOOGLE_FLOW_GENERATE:
        params = params or {}
        return _run_canonical_script(
            "scripts/generate_google_flow_user.sh",
            timeout=960,
            source_commit=source_commit,
            env_extra={"AGENTOS_GOOGLE_MEDIA_PROMPT": str(params.get("prompt") or "")},
        )
    if action == ACTION_GOOGLE_VIDS_GENERATE:
        params = params or {}
        return _run_canonical_script(
            "scripts/generate_google_vids_user.sh",
            timeout=960,
            source_commit=source_commit,
            env_extra={"AGENTOS_GOOGLE_MEDIA_PROMPT": str(params.get("prompt") or "")},
        )
    if action == ACTION_NODE_TRANSACTIONAL_OTA:
        params=params or {}
        return _run_canonical_script(
            "scripts/run_realm_node_transactional_ota_user.sh",
            timeout=480,
            source_commit=source_commit,
            env_extra={
                "AGENTOS_OTA_NODE_ID": str(params.get("node_id") or ""),
                "AGENTOS_OTA_CANDIDATE_COMMIT": str(params.get("candidate_commit") or ""),
            },
        )
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
    if action == ACTION_RECONCILE_CONTENT_SOCIAL:
        params = params or {}
        return _run_canonical_script(
            "scripts/reconcile_content_social_account_user.sh",
            timeout=780,
            source_commit=source_commit,
            env_extra={"AGENTOS_CONTENT_SOCIAL_ACCOUNT_REF": str(params.get("account_ref") or "")},
        )
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
    if action == ACTION_ACTIVATE_OURSONG_PERSONA:
        return _run_canonical_script(
            "scripts/activate_oursong_persona_user.sh",
            timeout=240,
            source_commit=source_commit,
        )
    if action == ACTION_PROBE_OURSONG_PERSONA:
        return _run_canonical_script(
            "scripts/probe_oursong_persona_user.sh",
            timeout=60,
            source_commit=source_commit,
        )
    if action == ACTION_PROBE_PERSONA_PDCA_RUNTIME:
        return _run_canonical_script(
            "scripts/probe_mio_pdca_runtime_origin_user.sh",
            timeout=90,
            source_commit=source_commit,
        )
    if action == ACTION_EXECUTOR_JOB_SUBMIT:
        params = params or {}
        from agent_core.executor_job_contract import canonical_executor_job_request
        from agentos_node.executor_job_action_relay import ActionRelayExecutorJobDispatcher
        request = canonical_executor_job_request(str(params.get("job_type") or ""))
        submission = ActionRelayExecutorJobDispatcher().submit(
            node_id="oracle-core-node",
            request=request,
        )
        return {"ok": True, "executor_job": submission}
    if action == ACTION_EXECUTOR_JOB_INSPECT:
        params = params or {}
        from agent_core.executor_job_contract import validate_executor_job_id
        from agentos_node.executor_job_action_relay import ActionRelayExecutorJobDispatcher
        job_id = validate_executor_job_id(str(params.get("job_id") or ""))
        receipt = ActionRelayExecutorJobDispatcher().inspect(job_id)
        return {
            "ok": True,
            "executor_job_state": "completed" if receipt is not None else "pending",
            "executor_job_receipt": receipt,
        }
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
