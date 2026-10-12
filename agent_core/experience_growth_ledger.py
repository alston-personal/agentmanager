"""ONE-native Experience Growth Ledger for issue #1768.

The accepted Experience set remains canonical. This ledger stores only bounded
provenance/delta metadata so AgentOS can distinguish executor assertions from
durable ONE-side acceptance and measure idempotent change over time.
"""
from __future__ import annotations

from contextlib import contextmanager
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Iterator

import fcntl

from agent_core.experience_store import validate_set

LEDGER_SCHEMA = "agentos.experience-growth-ledger/v1"
ATTEMPT_SCHEMA = "agentos.experience-return-attempt/v1"
VALID_CLASSIFICATIONS = {
    "accepted_new",
    "accepted_update",
    "duplicate_noop",
    "conflict_pending_review",
    "rejected",
    "failed",
    "asserted_only",
    "unknown",
}


def _data_root() -> Path:
    return Path(
        os.environ.get(
            "AGENT_DATA_ROOT",
            os.environ.get("AGENTOS_DATA_ROOT", "/home/ubuntu/agent-data"),
        )
    ).expanduser()


def ledger_path(project_id: str, *, data_root: Path | None = None) -> Path:
    project_id = str(project_id or "").strip()
    if not project_id or "/" in project_id or "\\" in project_id or project_id in {".", ".."}:
        raise ValueError("invalid project_id")
    root = data_root or _data_root()
    return root / "experience" / project_id / "growth-ledger.json"


def _canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _digest(value: Any) -> str:
    return "sha256:" + sha256(_canonical_bytes(value)).hexdigest()


def _artifact_fingerprints(value: dict[str, Any]) -> dict[str, str]:
    validated = validate_set(value)
    return {
        str(item["experience_id"]): _digest(item)
        for item in validated["artifacts"]
    }


def classify_delta(
    before: dict[str, Any],
    after: dict[str, Any],
) -> dict[str, Any]:
    """Return content-hash delta without exposing Experience payloads."""
    before = validate_set(before)
    after = validate_set(after)
    if before["project_id"] != after["project_id"]:
        raise ValueError("experience set project mismatch")

    old = _artifact_fingerprints(before)
    new = _artifact_fingerprints(after)
    added = sorted(set(new) - set(old))
    removed = sorted(set(old) - set(new))
    updated = sorted(k for k in set(old).intersection(new) if old[k] != new[k])

    if added and not removed and not updated:
        classification = "accepted_new"
    elif updated or removed:
        classification = "accepted_update"
    else:
        classification = "duplicate_noop"

    return {
        "classification": classification,
        "before_count": len(old),
        "after_count": len(new),
        "added_ids": added,
        "updated_ids": updated,
        "removed_ids": removed,
        "before_digest": _digest(before),
        "after_digest": _digest(after),
    }


@contextmanager
def _lock(path: Path) -> Iterator[None]:
    lock = path.with_suffix(path.suffix + ".lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    if lock.is_symlink():
        raise ValueError("growth ledger lock path must not be a symlink")
    with lock.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _empty(project_id: str) -> dict[str, Any]:
    return {
        "schema": LEDGER_SCHEMA,
        "project_id": project_id,
        "attempts": [],
    }


def read_growth_ledger(
    project_id: str,
    *,
    data_root: Path | None = None,
) -> dict[str, Any]:
    path = ledger_path(project_id, data_root=data_root)
    if path.is_symlink():
        raise ValueError("growth ledger path must not be a symlink")
    if not path.exists():
        return _empty(project_id)
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema") != LEDGER_SCHEMA or value.get("project_id") != project_id:
        raise ValueError("invalid growth ledger")
    attempts = value.get("attempts")
    if not isinstance(attempts, list):
        raise ValueError("growth ledger attempts must be a list")
    return value


def _atomic_write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=path.name + ".", suffix=".tmp", dir=str(path.parent)
    )
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(_canonical_bytes(value))
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp, 0o640)
        os.replace(tmp, path)
        dir_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    finally:
        tmp.unlink(missing_ok=True)


def append_attempt(
    *,
    project_id: str,
    attempt_id: str,
    executor_id: str,
    source_node: str,
    classification: str,
    timestamp: str,
    source_receipt: str | None = None,
    persisted_experience_ids: list[str] | None = None,
    before_count: int | None = None,
    after_count: int | None = None,
    before_digest: str | None = None,
    after_digest: str | None = None,
    growth_proof_status: str = "UNTESTED",
    data_root: Path | None = None,
) -> dict[str, Any]:
    classification = str(classification or "").strip()
    if classification not in VALID_CLASSIFICATIONS:
        raise ValueError("invalid classification")
    for field, value in {
        "attempt_id": attempt_id,
        "executor_id": executor_id,
        "source_node": source_node,
        "timestamp": timestamp,
    }.items():
        if not str(value or "").strip():
            raise ValueError(f"{field} is required")

    record = {
        "schema": ATTEMPT_SCHEMA,
        "attempt_id": str(attempt_id),
        "executor_id": str(executor_id),
        "source_node": str(source_node),
        "classification": classification,
        "timestamp": str(timestamp),
        "source_receipt": source_receipt,
        "persisted_experience_ids": sorted(
            set(str(x) for x in (persisted_experience_ids or []) if str(x))
        ),
        "before_count": before_count,
        "after_count": after_count,
        "before_digest": before_digest,
        "after_digest": after_digest,
        "growth_proof_status": str(growth_proof_status or "UNTESTED"),
        "credential_exposed": False,
    }
    record_digest = _digest(record)

    path = ledger_path(project_id, data_root=data_root)
    with _lock(path):
        ledger = read_growth_ledger(project_id, data_root=data_root)
        existing = next(
            (x for x in ledger["attempts"] if x.get("attempt_id") == attempt_id),
            None,
        )
        if existing is not None:
            if _digest(existing) != record_digest:
                raise ValueError("attempt_id already exists with different content")
            return {
                "ok": True,
                "appended": False,
                "attempt_id": attempt_id,
                "record_digest": record_digest,
                "credential_exposed": False,
            }

        ledger["attempts"].append(record)
        _atomic_write(path, ledger)

    return {
        "ok": True,
        "appended": True,
        "attempt_id": attempt_id,
        "record_digest": record_digest,
        "credential_exposed": False,
    }


def growth_status(
    project_id: str,
    *,
    executor_id: str | None = None,
    source_node: str | None = None,
    data_root: Path | None = None,
) -> dict[str, Any]:
    """Read-only bounded status projection for ONE/ChatGPT/other executors."""
    ledger = read_growth_ledger(project_id, data_root=data_root)
    attempts = [
        x
        for x in ledger["attempts"]
        if (executor_id is None or x.get("executor_id") == executor_id)
        and (source_node is None or x.get("source_node") == source_node)
    ]
    last_attempt = attempts[-1] if attempts else None
    accepted = [
        x
        for x in attempts
        if x.get("classification") in {"accepted_new", "accepted_update", "duplicate_noop"}
        and x.get("after_digest")
    ]
    last_success = accepted[-1] if accepted else None
    return {
        "schema": "agentos.experience-growth-status/v1",
        "project_id": project_id,
        "executor_id": executor_id,
        "source_node": source_node,
        "attempt_count": len(attempts),
        "accepted_attempt_count": len(accepted),
        "last_attempt": last_attempt,
        "last_success": last_success,
        "growth_proof_status": (
            last_attempt.get("growth_proof_status") if last_attempt else "UNTESTED"
        ),
        "credential_exposed": False,
    }
