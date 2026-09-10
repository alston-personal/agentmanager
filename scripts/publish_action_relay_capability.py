#!/usr/bin/env python3
from __future__ import annotations

import argparse
import grp
import json
import os
from pathlib import Path
import sys
import tempfile

# This helper is intentionally executable by absolute file path from the governed
# bootstrap boundary. Anchor imports at the immutable runtime root so
# `scripts/agentos_node.py` cannot shadow the real `agentos_node` package through
# Python's script-directory sys.path[0].
SCRIPT_DIR = Path(__file__).resolve().parent
RUNTIME_ROOT = SCRIPT_DIR.parent
sys.path = [entry for entry in sys.path if Path(entry or ".").resolve() != SCRIPT_DIR]
sys.path.insert(0, str(RUNTIME_ROOT))

from agentos_node.runtime_converge_action_relay import capability_marker_payload

SHARED_GROUP = "agentos"


def publish(marker: Path, *, source_ref: str, source_commit: str) -> dict:
    expected_gid = grp.getgrnam(SHARED_GROUP).gr_gid
    if os.getegid() != expected_gid:
        raise PermissionError(
            f"capability publisher must run with effective group {SHARED_GROUP}: "
            f"egid={os.getegid()} expected={expected_gid}"
        )
    if not marker.parent.is_dir():
        raise FileNotFoundError(f"Action Relay spool missing: {marker.parent}")
    parent = marker.parent.stat()
    if parent.st_gid != expected_gid:
        raise PermissionError("Action Relay spool is not owned by the agentos group boundary")

    payload = capability_marker_payload(source_ref=source_ref, source_commit=source_commit)
    fd, tmp_name = tempfile.mkstemp(
        prefix=".capabilities-",
        suffix=".tmp",
        dir=str(marker.parent),
        text=True,
    )
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp, 0o640)
        os.replace(tmp, marker)
        os.chown(marker, -1, expected_gid)
        dir_fd = os.open(marker.parent, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    finally:
        tmp.unlink(missing_ok=True)

    observed = json.loads(marker.read_text(encoding="utf-8"))
    if observed != payload:
        raise RuntimeError("Action Relay capability marker verification failed")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish the fixed Action Relay capability marker")
    parser.add_argument("--marker", required=True)
    parser.add_argument("--source-ref", required=True)
    parser.add_argument("--source-commit", required=True)
    args = parser.parse_args()
    publish(Path(args.marker), source_ref=args.source_ref, source_commit=args.source_commit)
    print("action_relay_capability_atomic_publish=PASS")
    print("action_relay_capability_group_context=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
