#!/usr/bin/env python3
"""Sanitize Antigravity worker/receipt state for one Issue #117 regression run.

Reads only the two capsule ids already emitted by the regression result plus the
worker-ready marker. It never dumps environment variables, prompts, capsule input,
or arbitrary relay files.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path("/home/ubuntu/agent-data/runtime/antigravity-relay")
SAFE_RECEIPT_KEYS = {
    "schema", "capsule_id", "ok", "status", "stage", "error", "error_code",
    "reason", "message", "worker_id", "executor", "executor_user", "returncode",
    "timed_out", "started_at", "finished_at", "created_at", "failed_at",
}
SAFE_WORKER_KEYS = {
    "schema", "worker_id", "executor", "executor_user", "pid", "started_at",
    "ready_at", "version", "status",
}


def safe_scalar(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        # Bound messages; do not preserve multiline/log-sized values.
        return value.replace("\r", " ").replace("\n", " ")[:1000]
    return None


def safe_subset(data: Any, allowed: set[str]) -> dict[str, Any]:
    if not isinstance(data, dict):
        return {}
    result: dict[str, Any] = {}
    for key in sorted(allowed):
        if key in data:
            value = safe_scalar(data[key])
            if value is not None or data[key] is None:
                result[key] = value
    return result


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"read_error": f"{type(exc).__name__}: {exc}"}


def locate_receipt(capsule_id: str) -> tuple[str, Path | None]:
    for bucket in ("receipts", "failed", "processing", "pending"):
        path = ROOT / "spool" / bucket / f"{capsule_id}.json"
        if path.exists():
            return bucket, path
    return "missing", None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--regression", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    regression = read_json(Path(args.regression))
    antigravity = regression.get("executors", {}).get("antigravity", {}) if isinstance(regression, dict) else {}
    capsule_ids: list[str] = []
    for side in ("baseline", "hydrated"):
        run = antigravity.get(side, {}).get("run", {}) if isinstance(antigravity, dict) else {}
        capsule_id = run.get("capsule_id") if isinstance(run, dict) else None
        if isinstance(capsule_id, str) and capsule_id:
            capsule_ids.append(capsule_id)

    worker_path = ROOT / "spool" / "worker-ready.json"
    worker_raw = read_json(worker_path) if worker_path.exists() else {}
    worker = safe_subset(worker_raw, SAFE_WORKER_KEYS)
    pid = worker.get("pid")
    proc_exe = None
    if isinstance(pid, int) or (isinstance(pid, str) and pid.isdigit()):
        try:
            proc_exe = str((Path("/proc") / str(pid) / "exe").resolve())
        except Exception:
            proc_exe = None

    result: dict[str, Any] = {
        "schema": "agentos.antigravity-regression-diagnostic/v0",
        "relay_root_present": ROOT.exists(),
        "worker_ready_present": worker_path.exists(),
        "worker": worker,
        "worker_proc_exe": proc_exe,
        "capsules": [],
        "redaction": "Only allowlisted scalar receipt/worker fields are persisted; prompts, environment, raw logs, stdout/stderr, argv, and arbitrary files are excluded.",
    }
    for capsule_id in capsule_ids:
        bucket, path = locate_receipt(capsule_id)
        raw = read_json(path) if path else {}
        result["capsules"].append({
            "capsule_id": capsule_id,
            "bucket": bucket,
            "receipt": safe_subset(raw, SAFE_RECEIPT_KEYS),
        })

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "worker_ready_present": result["worker_ready_present"],
        "worker": result["worker"],
        "worker_proc_exe": result["worker_proc_exe"],
        "capsules": result["capsules"],
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
