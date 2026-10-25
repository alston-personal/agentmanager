"""Fail-closed entry point for the bounded Claw review runner.

A runnable module is not an independent reviewer. Until a governed evidence
reader and independent executor are attached, do not claim/finish an assignment
or emit a PASS receipt. The adapter must remain disabled.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


SCHEMA = "agentos.claw-review-readonly-worker-cli-result/v1"


def _absolute(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise argparse.ArgumentTypeError("claw_worker_path_must_be_absolute")
    return path.resolve()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="claw-review-readonly")
    parser.add_argument("--runtime-root", type=_absolute, required=True)
    parser.add_argument("--wake-root", type=_absolute, required=True)
    parser.add_argument("--worker-state-root", type=_absolute, required=True)
    parser.add_argument("--node-id", required=True)
    parser.add_argument("--wake-id", required=True)
    parser.add_argument("--presence-generation", type=int, required=True)
    parser.add_argument("--once", action="store_true", required=True)
    args = parser.parse_args(argv)
    if args.presence_generation < 1 or not args.wake_id.strip() or not args.node_id.strip():
        parser.error("invalid_exact_claw_wake")
    print(json.dumps({
        "schema": SCHEMA,
        "status": "blocked",
        "work_performed": False,
        "error_code": "claw_independent_review_executor_unavailable",
        "credential_exposed": False,
        "session_identity_exposed": False,
        "verified_marker_emitted": False,
    }, sort_keys=True))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
