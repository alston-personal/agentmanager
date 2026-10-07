from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from agentos_node import bootstrap_control as bc


@dataclass(frozen=True, slots=True)
class ActionPolicy:
    role: str
    priority: int
    priority_label: str
    capabilities: tuple[str, ...] = ()
    locks: tuple[str, ...] = ()
    queue_ttl_seconds: float | None = None


HIGH = 10
NORMAL = 30
PUBLISH = 40
LOW = 60
MAINTENANCE = 70

POLICIES: dict[str, ActionPolicy] = {
    bc.ACTION_RUNNER_WINDOW_PROBE: ActionPolicy("control", 8, "high", ("agentos.dispatch.probe",), ()),
    bc.ACTION_RELAY_STATUS: ActionPolicy("control", 9, "high", ("agentos.relay.inspect",), ()),
    bc.ACTION_SCHEDULER_STATUS: ActionPolicy("control", 9, "high", ("agentos.scheduler.inspect",), ()),
    bc.ACTION_RELAY_RESTART: ActionPolicy("control", 7, "high", ("agentos.relay.restart",), ("oracle-antigravity-relay",)),
    bc.ACTION_EXECUTOR_JOB_SUBMIT: ActionPolicy("build", 20, "high", ("agentos.executor.job",), ()),
    bc.ACTION_EXECUTOR_JOB_INSPECT: ActionPolicy("build", 20, "high", ("agentos.executor.job",), ()),
    bc.ACTION_GITHUB_ACTIONS_DISPATCH: ActionPolicy("control", 18, "high", ("github.actions.dispatch",), ("github-actions-dispatch",)),
    bc.ACTION_NODE_TRANSACTIONAL_OTA: ActionPolicy("maintenance", 16, "high", ("node.runtime.ota",), ("node-runtime-ota",)),
    bc.ACTION_REALM_NODE_INSPECT: ActionPolicy("control", 9, "high", ("node.realm.inspect",), ()),
    bc.ACTION_REALM_DESKTOP_PROBE: ActionPolicy("control", 10, "high", ("node.desktop.probe",), ()),
    bc.ACTION_REALM_EXECUTOR_RECONCILE: ActionPolicy("control", 10, "high", ("node.executor.reconcile",), ()),
    bc.ACTION_GOOGLE_FLOW_GENERATE: ActionPolicy("gui", 16, "high", ("media.google-flow.generate", "browser.cdp", "browser.persistent_profile"), ("oracle-gui-profile", "google-media-flow")),
    bc.ACTION_GOOGLE_FLOW_RECOVER: ActionPolicy("gui", 16, "high", ("media.google-flow.recover", "browser.cdp", "browser.persistent_profile"), ("oracle-gui-profile", "google-media-flow")),
    bc.ACTION_GOOGLE_FLOW_RAIN_EXIT_RESUME: ActionPolicy("gui", 17, "high", ("media.google-flow.rain-exit-s01.resume-approved", "browser.cdp", "browser.persistent_profile"), ("oracle-gui-profile", "google-media-flow", "vision-studio-rain-exit")),
    bc.ACTION_GOOGLE_VIDS_GENERATE: ActionPolicy("gui", 16, "high", ("media.google-vids.generate", "browser.cdp", "browser.persistent_profile"), ("oracle-gui-profile", "google-media-vids")),
    bc.ACTION_VISION_STUDIO_PRODUCE: ActionPolicy("gui", 17, "high", ("media.vision-studio.produce", "media.google-flow.generate", "browser.cdp", "browser.persistent_profile"), ("oracle-gui-profile", "vision-studio-rain-exit")),
    bc.ACTION_REPAIR_TRANSPORT: ActionPolicy("maintenance", 5, "high", ("node.runtime.repair",), ("oracle-core-runtime",)),
    bc.ACTION_READ_THREADS_WEB_DM: ActionPolicy("gui", HIGH, "high", ("threads.gui.read",), ("oracle-gui-profile", "threads-mio-gui")),
    bc.ACTION_READ_OURSONG_THREADS_WEB_DM: ActionPolicy("gui", HIGH, "high", ("threads.gui.read", "persona.social.dm.read"), ("oracle-gui-profile", "threads-oursong-gui")),
    bc.ACTION_PROBE_THREADS_WEB_DM_LOGIN: ActionPolicy("gui", HIGH, "high", ("threads.gui.read",), ("oracle-gui-profile", "threads-mio-gui")),
    bc.ACTION_START_THREADS_WEB_DM_LOGIN: ActionPolicy("gui", HIGH, "high", ("threads.gui.write",), ("oracle-gui-profile", "threads-mio-gui"), queue_ttl_seconds=90),
    bc.ACTION_START_OURSONG_THREADS_WEB_DM_LOGIN: ActionPolicy("gui", HIGH, "high", ("threads.gui.write", "persona.social.dm.login"), ("threads-oursong-gui",), queue_ttl_seconds=90),
    bc.ACTION_INSTALL_OURSONG_THREADS_SESSION: ActionPolicy("maintenance", 22, "high", ("browser.persistent_profile", "persona.social.dm.session"), ("threads-oursong-session",)),
    bc.ACTION_INSTALL_MIO_THREADS_SESSION_SUPERVISOR: ActionPolicy("maintenance", 25, "normal", ("monitor.install",), ("oracle-core-runtime",)),
    bc.ACTION_ACCEPT_MIO_DM_OURSONG: ActionPolicy("gui", 11, "high", ("threads.gui.write",), ("oracle-gui-profile", "threads-mio-gui"), queue_ttl_seconds=120),
    bc.ACTION_ACCEPT_OURSONG_DM_MIO_ROUNDTRIP: ActionPolicy("gui", 12, "high", ("threads.gui.read", "threads.gui.write", "persona.social.dm.roundtrip"), ("threads-mio-gui", "threads-oursong-gui"), queue_ttl_seconds=150),
    bc.ACTION_PROBE_THREADS_WEB_DM: ActionPolicy("gui", 15, "high", ("threads.gui.read",), ("oracle-gui-profile", "threads-mio-gui")),
    bc.ACTION_PROBE_CHATGPT_WEB: ActionPolicy("gui", 12, "high", ("chatgpt.web.session", "browser.cdp", "browser.persistent_profile"), ("oracle-gui-profile",)),
    bc.ACTION_ACCEPT_CHATGPT_WEB_SESSION: ActionPolicy("gui", 14, "high", ("chatgpt.web.session", "agent.session.attach", "agent.session.inspect", "agent.context.inject"), ("oracle-gui-profile",)),
    bc.ACTION_INSTALL_CHATGPT_WEB_BRIDGE: ActionPolicy("gui", 22, "normal", ("chatgpt.web.session", "browser.cdp", "browser.persistent_profile"), ("oracle-gui-profile",)),
    bc.ACTION_PROBE_GEMINI_WEB: ActionPolicy("gui", 12, "high", ("gemini.web.session", "browser.cdp", "browser.persistent_profile"), ("oracle-gui-profile",)),
    bc.ACTION_ACCEPT_GEMINI_WEB_SESSION: ActionPolicy("gui", 14, "high", ("gemini.web.session", "agent.session.attach", "agent.session.inspect", "agent.context.inject"), ("oracle-gui-profile",)),
    bc.ACTION_START_GEMINI_WEB_LOGIN: ActionPolicy("gui", HIGH, "high", ("gemini.web.session", "desktop.remote_view", "browser.gui"), ("oracle-gui-profile",), queue_ttl_seconds=90),
    bc.ACTION_ACCEPT_GEMINI_WEB_ROUNDTRIP: ActionPolicy("gui", 14, "high", ("gemini.web.session", "agent.context.inject", "agent.context.harvest"), ("oracle-gui-profile",)),
    bc.ACTION_INSTALL_GEMINI_WEB_BRIDGE: ActionPolicy("gui", 22, "normal", ("gemini.web.session", "browser.cdp", "browser.persistent_profile"), ("oracle-gui-profile",)),
    bc.ACTION_RUN_MIO_DM_DECISION: ActionPolicy("social", 18, "high", ("mio.dm.decide",)),
    bc.ACTION_PAUSE_MIO_AUTOREPLY: ActionPolicy("control", 20, "high", ("mio.incident.repair",), ("oracle-core-runtime",)),
    bc.ACTION_INSPECT_MIO_SQUIRREL: ActionPolicy("social", NORMAL, "normal", ("threads.api.read",)),
    bc.ACTION_INSPECT_MIO_RECENT: ActionPolicy("social", NORMAL, "normal", ("threads.api.read",)),
    bc.ACTION_PUBLISH_MIO_APPROVED: ActionPolicy("social", PUBLISH, "normal", ("threads.api.write",), ("mio-publish",)),
    bc.ACTION_PUBLISH_MIO_DAY2: ActionPolicy("social", PUBLISH, "normal", ("threads.api.write",), ("mio-publish",)),
    bc.ACTION_PUBLISH_GALAXY_DAY1: ActionPolicy("social", PUBLISH, "normal", ("threads.api.write",), ("threads:oursong",)),
    bc.ACTION_PUBLISH_SUNLAKE_PERSONA_REPLIES: ActionPolicy("social", PUBLISH, "normal", ("threads.api.write",), ("threads:oursong",)),
    bc.ACTION_PROBE_MIO_IMAGE_CONTAINER: ActionPolicy("build", 45, "normal", ("asset.processing",)),
    bc.ACTION_PROJECT_MIO_OBSERVER: ActionPolicy("maintenance", LOW, "low", ("observer.update",), ("oracle-core-runtime",)),
    bc.ACTION_DEPLOY_STUDIO_WEB_MIO: ActionPolicy("maintenance", LOW, "low", ("deployment",), ("oracle-core-runtime",)),
    bc.ACTION_INSTALL_GALAXY_EXPERIMENT_MONITOR: ActionPolicy("maintenance", LOW, "low", ("monitor.install",), ("oracle-core-runtime",)),
    bc.ACTION_MIGRATE_GALAXY_EXPERIMENT_MONITOR: ActionPolicy("maintenance", LOW, "low", ("monitor.install",), ("oracle-core-runtime",)),
    bc.ACTION_INSTALL_MIO_OBSERVER_TIMER: ActionPolicy("maintenance", LOW, "low", ("monitor.install",), ("oracle-core-runtime",)),
    bc.ACTION_DEPLOY_SOCIAL_RUNTIME: ActionPolicy("maintenance", MAINTENANCE, "low", ("node.runtime.converge",), ("oracle-core-runtime",)),
    bc.ACTION_RECONCILE_CONTENT_SOCIAL: ActionPolicy("maintenance", 35, "normal", ("content.social.reconcile",), ("content-social-runtime",)),
    bc.ACTION_DEPLOY_THREADS_GALAXY: ActionPolicy("maintenance", MAINTENANCE, "low", ("deployment",), ("oracle-core-runtime",)),
    bc.ACTION_RECONCILE_CONTROL_INBOX: ActionPolicy("maintenance", MAINTENANCE, "low", ("node.runtime.converge",), ("oracle-core-runtime",)),
    bc.ACTION_DEPLOY_REALM_GATEWAY: ActionPolicy("maintenance", MAINTENANCE, "low", ("node.runtime.converge",), ("oracle-core-runtime",)),
    bc.ACTION_PROVISION_ZIWEI_MASTER_REPO: ActionPolicy("maintenance", MAINTENANCE, "low", ("repository.provision",), ("oracle-core-runtime",)),
    bc.ACTION_DEPLOY_MIO_TELEGRAM: ActionPolicy("maintenance", MAINTENANCE, "low", ("deployment",), ("oracle-core-runtime",)),
    bc.ACTION_INSTALL_GUI_WORKER: ActionPolicy("maintenance", MAINTENANCE, "low", ("node.gui.install",), ("oracle-core-runtime",)),
    bc.ACTION_SMOKE_GUI_WORKER: ActionPolicy("gui", 25, "normal", ("browser.cdp", "browser.gui"), ("oracle-gui-profile",)),
    bc.ACTION_DEPLOY_MIO_TRYON: ActionPolicy("maintenance", MAINTENANCE, "low", ("deployment",), ("oracle-core-runtime",)),
    bc.ACTION_INSTALL_ORACLE_EXEC: ActionPolicy("maintenance", MAINTENANCE, "low", ("node.runtime.converge",), ("oracle-core-runtime",)),
}

DEFAULT_POLICY = ActionPolicy("control", MAINTENANCE, "low", ("agentos.bootstrap.execute",), ("oracle-core-runtime",))
_LOCK_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class LockTimeout(RuntimeError):
    def __init__(self, lock_key: str):
        super().__init__("lock_timeout:" + lock_key)
        self.lock_key = lock_key


def data_root() -> Path:
    return Path(os.environ.get("AGENT_DATA_ROOT") or "/home/ubuntu/agent-data")


def state_root() -> Path:
    return data_root() / "runtime" / "bootstrap-scheduler"


def policy_for(action: str) -> ActionPolicy:
    return POLICIES.get(str(action or ""), DEFAULT_POLICY)


def _safe_worker_id(value: str) -> str:
    value = str(value or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", value):
        raise ValueError("invalid worker_id")
    return value


def _request_summary(path: Path) -> tuple[int, str, str, dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        payload = {}
    action = str(payload.get("action") or "unknown")
    policy = policy_for(action)
    created = str(payload.get("created_at") or "")
    return policy.priority, created, path.name, payload


def _queue_depths(requests: Path) -> dict[str, int]:
    depths = {"control": 0, "maintenance": 0, "social": 0, "gui": 0, "build": 0}
    for path in requests.glob("*.request.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            payload = {}
        role = policy_for(str(payload.get("action") or "")).role
        depths[role] = depths.get(role, 0) + 1
    return depths


def _write_status(worker_id: str, role: str, *, state: str, current: dict[str, Any] | None = None) -> None:
    root = state_root()
    root.mkdir(parents=True, exist_ok=True)
    lock_path = root / "status.lock"
    status_path = root / "status.json"
    with lock_path.open("a+") as lock_handle:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
        try:
            doc = json.loads(status_path.read_text(encoding="utf-8")) if status_path.exists() else {}
        except Exception:
            doc = {}
        requests, _, _ = bc._ensure(bc._root())
        workers = doc.get("workers") if isinstance(doc.get("workers"), dict) else {}
        workers[worker_id] = {
            "role": role,
            "state": state,
            "current_job": current,
            "heartbeat": bc._now(),
        }
        payload = {
            "schema": "agentos.bootstrap-scheduler-status/v1",
            "node": "oracle",
            "updated_at": bc._now(),
            "queue_depth": _queue_depths(requests),
            "workers": workers,
        }
        tmp = status_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(status_path)


def _incident(*, request_id: str, action: str, policy: ActionPolicy, failure_class: str,
              fallback_attempted: bool = False, detail: str | None = None) -> Path:
    root = state_root() / "incidents"
    root.mkdir(parents=True, exist_ok=True)
    project = "mio" if ("mio" in action or "web_dm" in action) else "agentos"
    payload: dict[str, Any] = {
        "schema": "agentos.scheduler-incident/v1",
        "project": project,
        "request_id": request_id,
        "action": action,
        "priority": policy.priority_label,
        "requested_capabilities": list(policy.capabilities),
        "preferred_node": "oracle",
        "failure_class": failure_class,
        "fallback_attempted": fallback_attempted,
        "receipt_required": True,
        "observed_at": bc._now(),
    }
    if detail:
        payload["detail"] = str(detail)[:240]
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", request_id)[:100] or "unknown"
    path = root / f"{safe}-{failure_class}-{int(time.time())}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


@contextmanager
def _held_locks(keys: tuple[str, ...], *, timeout_seconds: float = 120.0) -> Iterator[None]:
    handles = []
    lock_root = bc._root() / "locks"
    lock_root.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + max(0.1, timeout_seconds)
    try:
        for key in sorted(set(keys)):
            if not _LOCK_RE.fullmatch(key):
                raise ValueError("invalid lock key")
            handle = (lock_root / f"{key}.lock").open("a+")
            while True:
                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    handles.append(handle)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        handle.close()
                        raise LockTimeout(key)
                    time.sleep(0.2)
        yield
    finally:
        for handle in reversed(handles):
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            finally:
                handle.close()


def _expire_request(
    source: Path,
    payload: dict[str, Any],
    *,
    role: str,
    worker_id: str,
    receipts: Path,
    rejected: Path,
    failure_class: str = "queue_expired",
) -> None:
    request_id = source.name.removesuffix(".request.json")
    action = str(payload.get("action") or "unknown")
    policy = policy_for(action)
    age = _request_age_seconds(payload)
    receipt_path = receipts / f"{request_id}.json"
    if receipt_path.exists():
        source.unlink(missing_ok=True)
        return
    now = bc._now()
    receipt = {
        "schema": bc.RECEIPT_SCHEMA,
        "request_id": request_id,
        "action": action,
        "source_commit": str((payload.get("params") or {}).get("source_commit") or "") or None,
        "executor_user": os.environ.get("USER") or str(os.getuid()),
        "executor_uid": os.getuid(),
        "started_at": now,
        "completed_at": now,
        "ok": False,
        "failure_class": failure_class,
        "error": f"request exceeded scheduler queue lifetime: age={age:.1f}s",
        "scheduler": {
            "node": "oracle",
            "worker_role": role,
            "worker_id": worker_id,
            "priority": policy.priority_label,
            "requested_capabilities": list(policy.capabilities),
            "locks": list(policy.locks),
            "queue_ttl_seconds": policy.queue_ttl_seconds,
        },
    }
    bc._atomic_json(receipt_path, receipt)
    _incident(
        request_id=request_id,
        action=action,
        policy=policy,
        failure_class=failure_class,
        detail=f"age={int(age)}s;ttl={policy.queue_ttl_seconds}",
    )
    target = rejected / source.name
    target.unlink(missing_ok=True)
    source.replace(target)


def _recover_inflight(role: str, worker_id: str) -> dict[str, int]:
    """Recover requests orphaned when a role worker is restarted mid-job.

    A fresh orphan is atomically returned to the shared request queue.  A stale
    orphan receives a deterministic failure receipt instead of leaving ingress
    workflows waiting forever.  Existing receipts win, making recovery
    idempotent across repeated restarts.
    """
    worker_id = _safe_worker_id(worker_id)
    requests, receipts, rejected = bc._ensure(bc._root())
    inflight_dir = bc._root() / "inflight" / worker_id
    inflight_dir.mkdir(parents=True, exist_ok=True)
    recovered = 0
    completed = 0
    stale = 0
    for source in sorted(inflight_dir.glob("*.request.json")):
        request_id = source.name.removesuffix(".request.json")
        receipt_path = receipts / f"{request_id}.json"
        if receipt_path.exists():
            source.unlink(missing_ok=True)
            completed += 1
            continue
        try:
            payload = json.loads(source.read_text(encoding="utf-8"))
        except Exception:
            payload = {}
        action = str(payload.get("action") or "unknown")
        policy = policy_for(action)
        age = _request_age_seconds(payload)
        if policy.queue_ttl_seconds is not None and age > policy.queue_ttl_seconds:
            _expire_request(
                source,
                payload,
                role=role,
                worker_id=worker_id,
                receipts=receipts,
                rejected=rejected,
                failure_class="queue_expired",
            )
            stale += 1
            continue
        if age > bc.MAX_REQUEST_AGE_SECONDS:
            _expire_request(
                source,
                payload,
                role=role,
                worker_id=worker_id,
                receipts=receipts,
                rejected=rejected,
                failure_class="worker_restart_orphan_stale",
            )
            stale += 1
            continue
        destination = requests / source.name
        if destination.exists():
            # Another recovery path already requeued it; discard the duplicate
            # inflight inode rather than creating two executions.
            source.unlink(missing_ok=True)
            completed += 1
            continue
        os.rename(source, destination)
        recovered += 1
    return {"recovered": recovered, "completed": completed, "stale": stale}


def _supersede_older_idempotent_requests(
    role: str,
    worker_id: str,
    candidates: list[tuple[int, str, str, dict[str, Any]]],
) -> list[tuple[int, str, str, dict[str, Any]]]:
    """Complete redundant pending idempotent requests without executing them.

    A login-start request only asks the persistent GUI browser to expose the
    login page.  Replaying older generations after a worker restart can hang on
    obsolete browser drivers and provides no additional side effect.  Keep the
    newest pending login-start request and emit deterministic terminal receipts
    for older equivalents so ingress callers do not wait until timeout.
    """
    idempotent_actions = {bc.ACTION_START_THREADS_WEB_DM_LOGIN, bc.ACTION_PROBE_THREADS_WEB_DM_LOGIN}
    requests, receipts, rejected = bc._ensure(bc._root())
    dropped: set[str] = set()

    for action in idempotent_actions:
        rows = [
            item for item in candidates
            if str(item[3].get("action") or "") == action
            and policy_for(action).role == role
        ]
        if len(rows) <= 1:
            continue
        keep = max(rows, key=lambda item: (item[1], item[2]))
        policy = policy_for(action)
        for item in rows:
            if item is keep:
                continue
            _priority, _created, filename, payload = item
            source = requests / filename
            if not source.exists():
                continue
            request_id = filename.removesuffix(".request.json")
            source_commit = str((payload.get("params") or {}).get("source_commit") or "") or None
            receipt = {
                "schema": bc.RECEIPT_SCHEMA,
                "request_id": request_id,
                "action": action,
                "source_commit": source_commit,
                "executor_user": os.environ.get("USER") or str(os.getuid()),
                "executor_uid": os.getuid(),
                "started_at": bc._now(),
                "completed_at": bc._now(),
                "ok": False,
                "failure_class": "superseded",
                "error": "superseded_by_newer_equivalent_request",
                "scheduler": {
                    "node": "oracle",
                    "worker_role": role,
                    "worker_id": worker_id,
                    "priority": policy.priority_label,
                    "requested_capabilities": list(policy.capabilities),
                    "locks": list(policy.locks),
                    "superseded_by": keep[2].removesuffix(".request.json"),
                },
            }
            bc._atomic_json(receipts / f"{request_id}.json", receipt)
            target = rejected / source.name
            target.unlink(missing_ok=True)
            try:
                source.replace(target)
            except FileNotFoundError:
                continue
            dropped.add(filename)

    return [item for item in candidates if item[2] not in dropped]


def _claim(role: str, worker_id: str) -> tuple[Path, dict[str, Any]] | None:
    requests, receipts, rejected = bc._ensure(bc._root())
    candidates = sorted((_request_summary(path) for path in requests.glob("*.request.json")), key=lambda item: item[:3])
    candidates = _supersede_older_idempotent_requests(role, worker_id, candidates)
    inflight_dir = bc._root() / "inflight" / worker_id
    inflight_dir.mkdir(parents=True, exist_ok=True)
    for _priority, _created, filename, payload in candidates:
        action = str(payload.get("action") or "unknown")
        policy = policy_for(action)
        if policy.role != role:
            continue
        source = requests / filename
        if policy.queue_ttl_seconds is not None and _request_age_seconds(payload) > policy.queue_ttl_seconds:
            if source.exists():
                _expire_request(
                    source,
                    payload,
                    role=role,
                    worker_id=worker_id,
                    receipts=receipts,
                    rejected=rejected,
                    failure_class="queue_expired",
                )
            continue
        destination = inflight_dir / filename
        if destination.exists():
            continue
        try:
            os.rename(source, destination)
        except FileNotFoundError:
            continue
        return destination, payload
    return None


def run_once(role: str, worker_id: str, *, lock_timeout_seconds: float = 120.0) -> dict[str, Any] | None:
    worker_id = _safe_worker_id(worker_id)
    claim = _claim(role, worker_id)
    if claim is None:
        return None
    source, payload = claim
    requests, receipts, rejected = bc._ensure(bc._root())
    request_id = source.name.removesuffix(".request.json")
    action = str(payload.get("action") or "unknown")
    policy = policy_for(action)
    _write_status(worker_id, role, state="running", current={
        "request_id": request_id,
        "action": action,
        "priority": policy.priority_label,
        "locks": list(policy.locks),
    })
    started = bc._now()
    source_commit: str | None = None
    receipt: dict[str, Any]
    try:
        request_id, action, source_commit, post_key = bc._validate_request(source, payload)
        receipt_path = receipts / f"{request_id}.json"
        if receipt_path.exists():
            source.unlink(missing_ok=True)
            return json.loads(receipt_path.read_text(encoding="utf-8"))
        with _held_locks(policy.locks, timeout_seconds=lock_timeout_seconds):
            result = bc._execute(action, source_commit, post_key, payload.get("params") or {})
        receipt = {
            "schema": bc.RECEIPT_SCHEMA,
            "request_id": request_id,
            "action": action,
            "executor_user": os.environ.get("USER") or str(os.getuid()),
            "executor_uid": os.getuid(),
            "started_at": started,
            "completed_at": bc._now(),
            **result,
            "scheduler": {
                "node": "oracle",
                "worker_role": role,
                "worker_id": worker_id,
                "priority": policy.priority_label,
                "requested_capabilities": list(policy.capabilities),
                "locks": list(policy.locks),
            },
        }
        if receipt.get("ok") is not True:
            receipt["failure_class"] = "worker_failed"
            _incident(request_id=request_id, action=action, policy=policy, failure_class="worker_failed")
        bc._atomic_json(receipt_path, receipt)
        if receipt.get("ok") is True:
            source.unlink(missing_ok=True)
        else:
            target = rejected / source.name
            target.unlink(missing_ok=True)
            source.replace(target)
        return receipt
    except LockTimeout as exc:
        receipt = {
            "schema": bc.RECEIPT_SCHEMA,
            "request_id": request_id,
            "action": action,
            "source_commit": source_commit,
            "executor_user": os.environ.get("USER") or str(os.getuid()),
            "executor_uid": os.getuid(),
            "started_at": started,
            "completed_at": bc._now(),
            "ok": False,
            "failure_class": "lock_timeout",
            "error": str(exc),
            "scheduler": {
                "node": "oracle",
                "worker_role": role,
                "worker_id": worker_id,
                "priority": policy.priority_label,
                "requested_capabilities": list(policy.capabilities),
                "locks": list(policy.locks),
            },
        }
        bc._atomic_json(receipts / f"{request_id}.json", receipt)
        _incident(request_id=request_id, action=action, policy=policy, failure_class="lock_timeout", detail=exc.lock_key)
        target = rejected / source.name
        target.unlink(missing_ok=True)
        source.replace(target)
        return receipt
    except BaseException as exc:
        receipt = {
            "schema": bc.RECEIPT_SCHEMA,
            "request_id": request_id,
            "action": action,
            "source_commit": source_commit,
            "executor_user": os.environ.get("USER") or str(os.getuid()),
            "executor_uid": os.getuid(),
            "started_at": started,
            "completed_at": bc._now(),
            "ok": False,
            "failure_class": "worker_failed",
            "error": f"{type(exc).__name__}: {exc}"[:500],
            "scheduler": {
                "node": "oracle",
                "worker_role": role,
                "worker_id": worker_id,
                "priority": policy.priority_label,
                "requested_capabilities": list(policy.capabilities),
                "locks": list(policy.locks),
            },
        }
        bc._atomic_json(receipts / f"{request_id}.json", receipt)
        _incident(request_id=request_id, action=action, policy=policy, failure_class="worker_failed", detail=str(exc))
        target = rejected / source.name
        target.unlink(missing_ok=True)
        source.replace(target)
        return receipt
    finally:
        _write_status(worker_id, role, state="idle", current=None)



def _parse_time(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value or "").replace("Z", "+00:00")).astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _request_age_seconds(payload: dict[str, Any]) -> float:
    created = _parse_time(str(payload.get("created_at") or ""))
    if created is None:
        return 0.0
    return max(0.0, (datetime.now(timezone.utc) - created).total_seconds())


def _incident_once(*, request_id: str, action: str, policy: ActionPolicy, failure_class: str,
                   fallback_attempted: bool = False, detail: str | None = None) -> Path | None:
    marker_root = state_root() / "incident-markers"
    marker_root.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", request_id)[:100] or "unknown"
    marker = marker_root / f"{safe}.{failure_class}"
    try:
        fd = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return None
    else:
        os.close(fd)
    return _incident(
        request_id=request_id,
        action=action,
        policy=policy,
        failure_class=failure_class,
        fallback_attempted=fallback_attempted,
        detail=detail,
    )


def _gui_worker_state() -> tuple[str, bool]:
    path = state_root() / "status.json"
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return "unknown", True
    row = (doc.get("workers") or {}).get("oracle-gui") or {}
    state = str(row.get("state") or "unknown")
    heartbeat = _parse_time(str(row.get("heartbeat") or ""))
    stale = heartbeat is None or (datetime.now(timezone.utc) - heartbeat).total_seconds() > 20
    return state, stale


def _select_external_capability_candidate(
    nodes: list[dict[str, Any]],
    required_capabilities: tuple[str, ...],
) -> tuple[dict[str, Any] | None, str]:
    """Select the freshest online external node that satisfies every capability.

    Local Oracle execution is represented by role workers, not by Realm fallback
    candidates.  Keep the same-machine oracle-exec client out of this selector;
    every other client node competes by live capability and heartbeat freshness.
    """
    required = set(required_capabilities)
    external = [
        item
        for item in nodes
        if isinstance(item, dict)
        and item.get("role") != "core"
        and str(item.get("node_id") or "") != "oracle-exec"
    ]
    if not external:
        return None, "external_nodes_not_registered"

    online = [item for item in external if item.get("status") == "online"]
    if not online:
        return None, "external_nodes_offline"

    eligible = [
        item
        for item in online
        if required.issubset(set(item.get("capabilities") or []))
    ]
    if not eligible:
        return None, "external_nodes_missing_capability"

    def rank(item: dict[str, Any]) -> tuple[float, str]:
        age = item.get("heartbeat_age_seconds")
        try:
            freshness = float(age)
        except (TypeError, ValueError):
            freshness = float("inf")
        return freshness, str(item.get("node_id") or "")

    return min(eligible, key=rank), "ready"


def _external_capability_candidate(required_capabilities: tuple[str, ...]) -> tuple[dict[str, Any] | None, str]:
    try:
        from agent_core.node_registry import NodeRegistry
        nodes = NodeRegistry().node_map().get("nodes") or []
    except Exception as exc:
        return None, "node_registry_error:" + type(exc).__name__
    return _select_external_capability_candidate(nodes, required_capabilities)


def _merge_fallback_events(events: Any) -> int:
    if not isinstance(events, list) or not events:
        return 0
    root = Path.home() / ".local" / "share" / "agentos" / "social" / "threads-web-dm"
    path = root / "events.jsonl"
    root.mkdir(parents=True, exist_ok=True)
    os.chmod(root, 0o700)
    seen: set[str] = set()
    if path.exists():
        for raw in path.read_text(encoding="utf-8").splitlines()[-500:]:
            try:
                row = json.loads(raw)
            except Exception:
                continue
            if isinstance(row, dict) and row.get("message_id"):
                seen.add(str(row["message_id"]))
    appended = 0
    with path.open("a", encoding="utf-8") as handle:
        for event in events[:100]:
            if not isinstance(event, dict):
                continue
            message_id = str(event.get("message_id") or "")
            if not message_id or message_id in seen:
                continue
            safe = dict(event)
            safe["source"] = "realm_failover"
            handle.write(json.dumps(safe, ensure_ascii=False, separators=(",", ":")) + "\n")
            seen.add(message_id)
            appended += 1
    os.chmod(path, 0o600)
    return appended


def route_failover_once(*, worker_id: str = "agentos-router", failover_after_seconds: float = 5.0,
                        incident_after_seconds: float = 15.0, receipt_timeout_seconds: float = 90.0) -> dict[str, Any] | None:
    requests, receipts, _rejected = bc._ensure(bc._root())
    candidates = sorted((_request_summary(path) for path in requests.glob("*.request.json")), key=lambda item: item[:3])
    for _priority, _created, filename, payload in candidates:
        action = str(payload.get("action") or "")
        if action != bc.ACTION_READ_THREADS_WEB_DM:
            continue
        policy = policy_for(action)
        age = _request_age_seconds(payload)
        gui_state, gui_stale = _gui_worker_state()
        oracle_busy = gui_state == "running" or gui_stale
        if age < failover_after_seconds or not oracle_busy:
            continue

        request_id = filename.removesuffix(".request.json")
        candidate, candidate_reason = _external_capability_candidate(policy.capabilities)
        if candidate is None:
            if age >= incident_after_seconds:
                failure = "node_offline" if candidate_reason == "external_nodes_offline" else "capability_unavailable"
                _incident_once(
                    request_id=request_id,
                    action=action,
                    policy=policy,
                    failure_class=failure,
                    fallback_attempted=False,
                    detail=f"oracle_gui={gui_state};fallback={candidate_reason};queue_age={int(age)}s",
                )
                _incident_once(
                    request_id=request_id,
                    action=action,
                    policy=policy,
                    failure_class="queue_starvation",
                    fallback_attempted=False,
                    detail=f"oracle_gui={gui_state};fallback={candidate_reason};queue_age={int(age)}s",
                )
            continue

        source = requests / filename
        inflight_dir = bc._root() / "inflight" / worker_id
        inflight_dir.mkdir(parents=True, exist_ok=True)
        claimed = inflight_dir / filename
        try:
            os.rename(source, claimed)
        except FileNotFoundError:
            continue

        started = bc._now()
        try:
            request_id, action, source_commit, _post_key = bc._validate_request(claimed, payload)
            from agent_core.realm_fabric import RealmFabricStore
            store = RealmFabricStore()
            candidate_id = str(candidate.get("node_id") or "")
            if not candidate_id:
                raise RuntimeError("external_failover_candidate_missing_node_id")
            task_id = "scheduler-failover-" + hashlib.sha256(request_id.encode("utf-8")).hexdigest()[:24]
            existing = store.get_receipt(task_id)
            if existing is None:
                store.queue_task(
                    candidate_id,
                    {
                        "schema": "agentos.node-task/v0.1",
                        "task_id": task_id,
                        "action": "threads.gui.read",
                        "account": "mio.milkcat",
                        "source_commit": source_commit,
                        "cognition_ids_used": [],
                    },
                )
            deadline = time.monotonic() + max(5.0, receipt_timeout_seconds)
            remote = existing
            while remote is None and time.monotonic() < deadline:
                time.sleep(1.0)
                remote = store.get_receipt(task_id)
            if remote is None:
                raise TimeoutError(candidate_id + "_failover_receipt_timeout")
            if remote.get("ok") is not True:
                raise RuntimeError(candidate_id + "_failover_worker_failed")
            state = str(remote.get("threads_gui_read_state") or "UNKNOWN")
            if state not in {"PASS", "LOGIN_REQUIRED"}:
                raise RuntimeError(candidate_id + "_failover_invalid_state:" + state)

            appended = _merge_fallback_events(remote.get("events"))
            stdout = "\n".join(
                [
                    "threads_web_dm_bridge=" + ("PASS" if state == "PASS" else "LOGIN_REQUIRED"),
                    "threads_web_dm_new_events=" + str(int(remote.get("new_events") or 0)),
                    "threads_web_dm_inbound_events=" + str(int(remote.get("inbound_events") or 0)),
                    "threads_web_dm_failover_events_merged=" + str(appended),
                    "threads_web_dm_read=" + state,
                ]
            ) + "\n"
            receipt = {
                "schema": bc.RECEIPT_SCHEMA,
                "request_id": request_id,
                "action": action,
                "source_commit": source_commit,
                "executor_user": os.environ.get("USER") or str(os.getuid()),
                "executor_uid": os.getuid(),
                "started_at": started,
                "completed_at": bc._now(),
                "ok": True,
                "steps": [{"step": "realm_failover_threads_gui_read", "returncode": 0, "stdout": stdout, "stderr": ""}],
                "scheduler": {
                    "node": candidate_id,
                    "worker_role": "gui",
                    "worker_id": candidate_id,
                    "priority": policy.priority_label,
                    "requested_capabilities": list(policy.capabilities),
                    "locks": list(policy.locks),
                    "fallback_from": "oracle-gui",
                    "fallback_attempted": True,
                },
            }
            bc._atomic_json(receipts / f"{request_id}.json", receipt)
            claimed.unlink(missing_ok=True)
            return receipt
        except Exception as exc:
            _incident_once(
                request_id=request_id,
                action=action,
                policy=policy,
                failure_class="worker_failed",
                fallback_attempted=True,
                detail=f"{str(candidate.get('node_id') or 'external')}:{type(exc).__name__}:{exc}",
            )
            source = requests / filename
            if not source.exists() and claimed.exists():
                try:
                    os.rename(claimed, source)
                except OSError:
                    pass
            return None
    return None

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--role", choices=("control", "maintenance", "social", "gui", "build", "router"), required=True)
    parser.add_argument("--worker-id", required=True)
    parser.add_argument("--poll-seconds", type=float, default=0.75)
    parser.add_argument("--lock-timeout-seconds", type=float, default=120.0)
    args = parser.parse_args()
    worker_id = _safe_worker_id(args.worker_id)
    if args.role != "router":
        _recover_inflight(args.role, worker_id)
    _write_status(worker_id, args.role, state="idle", current=None)
    last_idle_heartbeat = time.monotonic()
    while True:
        if args.role == "router":
            receipt = route_failover_once(worker_id=worker_id)
        else:
            receipt = run_once(args.role, worker_id, lock_timeout_seconds=args.lock_timeout_seconds)
        if receipt is None:
            now = time.monotonic()
            if now - last_idle_heartbeat >= 10:
                _write_status(worker_id, args.role, state="idle", current=None)
                last_idle_heartbeat = now
            time.sleep(max(0.1, args.poll_seconds))
        else:
            last_idle_heartbeat = time.monotonic()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
