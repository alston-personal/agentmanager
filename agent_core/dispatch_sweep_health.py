"""Non-sensitive, process-scoped heartbeat for the existing runtime dispatch sweep.

This is observational state only: it is never used as task authority or a lease.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import time


def publish_sweep_heartbeat(path: str | os.PathLike[str], *, healthy: bool) -> None:
    """Atomically publish a heartbeat without leaking target/task/error details."""
    destination = Path(path)
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    record = {
        "schema": "agentos.dispatch-sweep-heartbeat/v1",
        "pid": os.getpid(),
        "observed_at_epoch": time.time(),
        "healthy": bool(healthy),
    }
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=destination.parent,
            prefix=".dispatch-sweep-", delete=False,
        ) as stream:
            temp_name = stream.name
            os.chmod(temp_name, 0o600)
            json.dump(record, stream, separators=(",", ":"), sort_keys=True)
            stream.write("\n")
        os.replace(temp_name, destination)
    finally:
        if temp_name is not None:
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass


def inspect_sweep_heartbeat(
    path: str | os.PathLike[str], *, expected_pid: int,
    process_started_epoch: float, interval_seconds: float,
    now_epoch: float | None = None,
) -> dict[str, object]:
    """Fail closed on missing, stale, mismatched or non-success heartbeat."""
    result: dict[str, object] = {
        "sweep_active_proven": False,
        "sweep_heartbeat_reason": "missing_or_unreadable",
    }
    if expected_pid <= 0 or interval_seconds <= 0:
        result["sweep_heartbeat_reason"] = "invalid_runtime_config"
        return result
    try:
        p = Path(path)
        if p.is_symlink() or not p.is_file() or p.stat().st_size > 2048:
            return result
        record = json.loads(p.read_text(encoding="utf-8"))
        if record.get("schema") != "agentos.dispatch-sweep-heartbeat/v1":
            result["sweep_heartbeat_reason"] = "unknown_schema"
            return result
        if type(record.get("pid")) is not int or record["pid"] != expected_pid:
            result["sweep_heartbeat_reason"] = "pid_mismatch"
            return result
        timestamp = record.get("observed_at_epoch")
        if type(timestamp) not in (float, int):
            result["sweep_heartbeat_reason"] = "bad_timestamp"
            return result
        now = time.time() if now_epoch is None else now_epoch
        age = now - timestamp
        if timestamp < process_started_epoch - 1 or age < -2 or age > max(30.0, 3 * interval_seconds):
            result["sweep_heartbeat_reason"] = "stale_or_future"
            return result
        if record.get("healthy") is not True:
            result["sweep_heartbeat_reason"] = "last_sweep_failed"
            return result
    except (OSError, ValueError, TypeError, AttributeError):
        return result
    result["sweep_active_proven"] = True
    result["sweep_heartbeat_reason"] = "fresh_success"
    return result
