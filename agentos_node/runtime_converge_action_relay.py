"""Bounded Oracle Core runtime convergence through the existing Action Relay.

The external capability is ``node.runtime.converge``.  The relay action below is
an implementation detail owned by the trusted ubuntu worker.  Callers provide
only the canonical typed request; executable names, argv, paths, environment,
service names and installer sequence are fixed here.
"""
from __future__ import annotations

import fcntl
import json
import os
import re
import subprocess
import urllib.request
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping

from agent_core.runtime_converge_contract import validate_runtime_converge_request
from agentos_node.action_relay import ACTIONS, ActionRelayClient


ACTION = "agentos.runtime.converge"
DEFAULT_RELAY_ROOT = Path("/home/ubuntu/agent-data/runtime/action-relay")
DEFAULT_REPO = Path("/home/ubuntu/agentmanager")
CAPABILITY_MARKER = DEFAULT_RELAY_ROOT / "capabilities.json"
REQUEST_ID_FIELDS = (
    "schema",
    "request_id",
    "node_id",
    "repository",
    "source_ref",
    "source_commit",
)
ALLOWED_ORIGIN_RE = re.compile(
    r"^(?:https://github\.com/|git@github\.com:|ssh://git@github\.com/)"
    r"alston-personal/agentmanager(?:\.git)?/?$"
)
SAFE_RESULT_FIELDS = (
    "request_id",
    "node_id",
    "repository",
    "source_ref",
    "source_commit",
    "previous_commit",
    "resulting_commit",
    "health",
    "rollback",
    "status",
    "classification",
    "idempotent",
    "credential_exposed",
    "observed_at",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _run(argv: list[str], *, cwd: Path, timeout: int = 180) -> subprocess.CompletedProcess[str]:
    """Run one trusted, source-owned command. Caller data never supplies argv."""
    return subprocess.run(
        argv,
        cwd=str(cwd),
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def _git(repo: Path, *args: str, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return _run(["git", *args], cwd=repo, timeout=timeout)


def _git_value(repo: Path, *args: str) -> str:
    result = _git(repo, *args)
    if result.returncode != 0:
        raise RuntimeError("git_preflight_failed")
    return result.stdout.strip()


def _health() -> bool:
    for unit in ("agentos-realm-fabric.service", "agentos-core-supervisor.service"):
        result = _run(["systemctl", "--user", "is-active", "--quiet", unit], cwd=DEFAULT_REPO, timeout=20)
        if result.returncode != 0:
            return False
    try:
        with urllib.request.urlopen("http://127.0.0.1:8780/v1/health", timeout=5) as response:
            if response.status != 200:
                return False
            payload = json.loads(response.read().decode("utf-8"))
            return isinstance(payload, dict) and payload.get("ok") is True
    except Exception:
        return False


def _install_fixed_runtime(repo: Path) -> bool:
    """Install only source-owned, fixed Core surfaces; never caller-selected code."""
    steps = (
        (["python3", "scripts/install_services.py"], 240),
        (["bash", "scripts/install_realm_fabric_user.sh"], 120),
        (["bash", "scripts/activate_product_employees_oracle.sh"], 240),
    )
    for argv, timeout in steps:
        result = _run(argv, cwd=repo, timeout=timeout)
        if result.returncode != 0:
            return False
    return _health()


def _checkout_exact(repo: Path, commit: str) -> bool:
    result = _git(repo, "checkout", "--detach", "--force", commit)
    return result.returncode == 0 and _git_value(repo, "rev-parse", "HEAD") == commit


def _preflight(repo: Path, request: Mapping[str, Any]) -> tuple[str, bool]:
    if not repo.is_dir() or not (repo / ".git").exists():
        raise RuntimeError("repo_unavailable")
    origin = _git_value(repo, "remote", "get-url", "origin")
    if not ALLOWED_ORIGIN_RE.fullmatch(origin):
        raise RuntimeError("repository_origin_not_allowed")
    dirty = _git_value(repo, "status", "--porcelain", "--untracked-files=no")
    if dirty:
        raise RuntimeError("tracked_checkout_dirty")

    previous = _git_value(repo, "rev-parse", "HEAD")
    source_ref = str(request["source_ref"])
    source_commit = str(request["source_commit"])
    fetched = _git(repo, "fetch", "--no-tags", "origin", source_ref)
    if fetched.returncode != 0:
        raise RuntimeError("source_fetch_failed")
    observed_head = _git_value(repo, "rev-parse", "FETCH_HEAD")
    if observed_head != source_commit:
        raise RuntimeError("exact_source_head_mismatch")
    return previous, previous == source_commit


def _safe_failure(request: Mapping[str, Any], classification: str, *, previous: str | None = None,
                  rollback: str = "not_attempted", resulting: str | None = None) -> dict[str, Any]:
    return {
        "request_id": request["request_id"],
        "node_id": request["node_id"],
        "repository": request["repository"],
        "source_ref": request["source_ref"],
        "source_commit": request["source_commit"],
        "previous_commit": previous,
        "resulting_commit": resulting,
        "health": "failed",
        "rollback": rollback,
        "status": "failed",
        "classification": classification,
        "idempotent": False,
        "credential_exposed": False,
        "observed_at": _utc_now(),
    }


def converge_runtime(request: Mapping[str, Any], *, repo: Path = DEFAULT_REPO) -> dict[str, Any]:
    """Converge exact source and reconcile its fixed operating profile.

    Source equality is not operating-profile equality.  Even when HEAD already
    equals the requested generation, the source-owned installer sequence is
    replayed idempotently so stopped services or missing host-local profile state
    cannot survive a successful convergence receipt.
    """
    canonical = validate_runtime_converge_request(request).as_payload()
    previous: str | None = None
    try:
        previous, idempotent = _preflight(repo, canonical)
    except RuntimeError as exc:
        return _safe_failure(canonical, str(exc))

    if idempotent:
        reconciled = _install_fixed_runtime(repo)
        return {
            "request_id": canonical["request_id"],
            "node_id": canonical["node_id"],
            "repository": canonical["repository"],
            "source_ref": canonical["source_ref"],
            "source_commit": canonical["source_commit"],
            "previous_commit": previous,
            "resulting_commit": previous,
            "health": "passed" if reconciled else "failed",
            "rollback": "not_needed",
            "status": "completed" if reconciled else "failed",
            "classification": "CURRENT_GENERATION_RECONCILED" if reconciled else "CURRENT_GENERATION_RECONCILE_FAILED",
            "idempotent": True,
            "credential_exposed": False,
            "observed_at": _utc_now(),
        }

    if not _checkout_exact(repo, canonical["source_commit"]):
        return _safe_failure(canonical, "target_checkout_failed", previous=previous)

    if _install_fixed_runtime(repo):
        return {
            "request_id": canonical["request_id"],
            "node_id": canonical["node_id"],
            "repository": canonical["repository"],
            "source_ref": canonical["source_ref"],
            "source_commit": canonical["source_commit"],
            "previous_commit": previous,
            "resulting_commit": canonical["source_commit"],
            "health": "passed",
            "rollback": "not_needed",
            "status": "completed",
            "classification": "CONVERGED",
            "idempotent": False,
            "credential_exposed": False,
            "observed_at": _utc_now(),
        }

    rollback_checkout = bool(previous) and _checkout_exact(repo, previous)
    rollback_health = rollback_checkout and _install_fixed_runtime(repo)
    if rollback_health:
        return _safe_failure(
            canonical,
            "TARGET_HEALTH_FAILED_ROLLED_BACK",
            previous=previous,
            rollback="completed",
            resulting=previous,
        )
    return _safe_failure(
        canonical,
        "ROLLBACK_OUTCOME_UNKNOWN",
        previous=previous,
        rollback="unknown",
        resulting=None,
    )


def _execute(params: dict[str, Any]) -> dict[str, Any]:
    if set(params) != {"request"} or not isinstance(params.get("request"), dict):
        raise ValueError("runtime-converge relay accepts only a canonical request object")
    result = converge_runtime(dict(params["request"]))
    return {key: result.get(key) for key in SAFE_RESULT_FIELDS}


if ACTION in ACTIONS and ACTIONS[ACTION] is not _execute:
    raise RuntimeError("runtime-converge Action Relay action already registered differently")
ACTIONS[ACTION] = _execute


def _read_object(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _request_from_capsule(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    if payload.get("action") != ACTION:
        return None
    params = payload.get("params")
    if not isinstance(params, Mapping):
        return None
    request = params.get("request")
    if not isinstance(request, Mapping):
        return None
    try:
        return validate_runtime_converge_request(request).as_payload()
    except (TypeError, ValueError):
        return None


def _request_from_receipt(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    if payload.get("action") != ACTION or not payload.get("request_id"):
        return None
    candidate = {key: payload.get(key) for key in REQUEST_ID_FIELDS}
    candidate["schema"] = "agentos.runtime-converge-request/v1"
    try:
        return validate_runtime_converge_request(candidate).as_payload()
    except (TypeError, ValueError):
        return None


def _same_request_id(canonical: Mapping[str, Any], observed: Mapping[str, Any]) -> bool:
    return str(observed.get("request_id") or "") == str(canonical["request_id"])


def _require_same_request(canonical: Mapping[str, Any], observed: Mapping[str, Any]) -> None:
    if not _same_request_id(canonical, observed):
        return
    for key in REQUEST_ID_FIELDS:
        if str(observed.get(key) or "") != str(canonical.get(key) or ""):
            raise RuntimeError("runtime_converge_request_id_collision")


@contextmanager
def _request_submit_lock(root: Path) -> Iterator[None]:
    root.mkdir(parents=True, exist_ok=True)
    lock_path = root / ".runtime-converge-submit.lock"
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o660)
    try:
        os.fchmod(fd, 0o660)
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def _existing_runtime_converge(root: Path, canonical: Mapping[str, Any]) -> tuple[str, str] | None:
    """Resolve one durable request-id execution without replaying ambiguity.

    Priority is intentionally conservative: a quarantined capsule with an
    ``outcome=unknown`` receipt wins over any duplicate success left by older
    buggy submitters.  A request whose execution outcome became unknown may not
    be replayed merely because another duplicate happened to finish later.
    """
    buckets = {name: root / name for name in ("inbox", "processing", "receipts", "quarantine")}

    # First bind quarantined raw capsules to their terminal unknown receipts.
    for capsule_path in sorted(buckets["quarantine"].glob("action-*.json")) if buckets["quarantine"].exists() else []:
        capsule = _read_object(capsule_path)
        if not capsule:
            continue
        observed = _request_from_capsule(capsule)
        if not observed or not _same_request_id(canonical, observed):
            continue
        _require_same_request(canonical, observed)
        capsule_id = str(capsule.get("capsule_id") or capsule_path.stem)
        receipt = _read_object(buckets["receipts"] / f"{capsule_id}.json")
        if receipt and receipt.get("outcome") == "unknown":
            return capsule_id, "unknown"

    # A terminal receipt is authoritative for a clean request-id history.
    for receipt_path in sorted(buckets["receipts"].glob("action-*.json")) if buckets["receipts"].exists() else []:
        receipt = _read_object(receipt_path)
        if not receipt:
            continue
        observed = _request_from_receipt(receipt)
        if not observed or not _same_request_id(canonical, observed):
            continue
        _require_same_request(canonical, observed)
        capsule_id = str(receipt.get("capsule_id") or receipt_path.stem)
        return capsule_id, "unknown" if receipt.get("outcome") == "unknown" else "completed"

    for bucket, state in (("processing", "processing"), ("inbox", "queued")):
        directory = buckets[bucket]
        for capsule_path in sorted(directory.glob("action-*.json")) if directory.exists() else []:
            capsule = _read_object(capsule_path)
            if not capsule:
                continue
            observed = _request_from_capsule(capsule)
            if not observed or not _same_request_id(canonical, observed):
                continue
            _require_same_request(canonical, observed)
            return str(capsule.get("capsule_id") or capsule_path.stem), state
    return None


class ActionRelayRuntimeConvergeDispatcher:
    def __init__(self, root: str | Path = DEFAULT_RELAY_ROOT):
        self.root = Path(root)
        self.client = ActionRelayClient(self.root)

    def submit(self, *, request: Mapping[str, Any]) -> dict[str, Any]:
        canonical = validate_runtime_converge_request(request).as_payload()
        with _request_submit_lock(self.root):
            existing = _existing_runtime_converge(self.root, canonical)
            if existing is None:
                capsule = self.client.submit(ACTION, {"request": canonical})
                task_id = str(capsule["capsule_id"])
                state = "queued"
            else:
                task_id, state = existing
        return {
            "schema": "agentos.runtime-converge-submission/v1",
            "ok": state != "unknown",
            "action": "node.runtime.converge",
            "task_id": task_id,
            "request_id": canonical["request_id"],
            "node_id": canonical["node_id"],
            "source_ref": canonical["source_ref"],
            "source_commit": canonical["source_commit"],
            "state": state,
            "deduplicated": existing is not None,
        }

    def inspect(self, task_id: str) -> dict[str, Any] | None:
        receipt = self.client.receipt(str(task_id))
        if receipt is None:
            return None
        if receipt.get("action") != ACTION:
            raise RuntimeError("runtime_converge_receipt_action_mismatch")
        projected = {key: receipt.get(key) for key in SAFE_RESULT_FIELDS if key in receipt}
        projected.update({
            "schema": "agentos.runtime-converge-receipt/v1",
            "ok": projected.get("status") == "completed",
            "action": "node.runtime.converge",
            "task_id": str(task_id),
        })
        if receipt.get("outcome") == "unknown":
            projected.update({"ok": False, "status": "unknown", "classification": "EXECUTION_OUTCOME_UNKNOWN"})
        return projected


def capability_marker_payload(*, source_ref: str, source_commit: str) -> dict[str, Any]:
    if source_ref != "core/integration" or not re.fullmatch(r"[0-9a-f]{40}", source_commit):
        raise ValueError("invalid Action Relay capability provenance")
    return {
        "schema": "agentos.action-relay-capabilities/v1",
        "actions": ["agentos.executor.job", ACTION],
        "node_capabilities": ["node.runtime.converge"],
        "source_ref": source_ref,
        "source_commit": source_commit,
        "observed_at": _utc_now(),
    }
