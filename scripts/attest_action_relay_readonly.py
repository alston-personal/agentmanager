#!/usr/bin/env python3
"""Read-only, redacted Action Relay installed-generation attestation.

Fixed Oracle ubuntu user service and fixed path; prints only allowlisted
statuses and Git commit IDs. Never prints units, argv, environment or paths.
No network, install, systemctl mutation, checkout, or recovery side effects.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

SCHEMA = "agentos.action-relay-live-readback/v1"
UNIT = "agentos-action-relay.service"
RUNTIME = Path("/home/ubuntu/.local/share/agentos/action-runtime")
MARKER = Path("/home/ubuntu/agent-data/runtime/action-relay/capabilities.json")
PENDING = RUNTIME.parent / ".action-relay-install.pending"
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
ALLOWED_REFS = frozenset({"main", "core/integration", "feature/realm-node-fabric-readiness"})


def command(*args: str) -> str | None:
    try:
        result = subprocess.run(
            list(args), check=False, capture_output=True, text=True, timeout=8
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def safe_marker(path: Path) -> dict | None:
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 65536:
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else None
    except (OSError, ValueError):
        return None


def assess(*, active: str | None, workdir: str | None, unit_environment: str | None,
           runtime_head: str | None, runtime_status: str | None, marker: dict | None,
           pending: bool, root: Path = RUNTIME) -> dict:
    """Pure evaluator; never output raw environment, unit or filesystem paths."""
    unit_fields = {}
    for token in (unit_environment or "").split():
        if token.startswith("AGENTOS_ACTION_RUNTIME_SOURCE_REF="):
            unit_fields["ref"] = token.split("=", 1)[1]
        elif token.startswith("AGENTOS_ACTION_RUNTIME_SOURCE_COMMIT="):
            unit_fields["sha"] = token.split("=", 1)[1]
    expected_ref = unit_fields.get("ref")
    expected_sha = unit_fields.get("sha")
    marker_ref = marker.get("source_ref") if marker else None
    marker_sha = marker.get("source_commit") if marker else None
    valid_head = isinstance(runtime_head, str) and bool(COMMIT_RE.fullmatch(runtime_head))
    valid_unit_sha = isinstance(expected_sha, str) and bool(COMMIT_RE.fullmatch(expected_sha))
    valid_marker_sha = isinstance(marker_sha, str) and bool(COMMIT_RE.fullmatch(marker_sha))
    try:
        workdir_match = (bool(workdir) and Path(workdir).resolve(strict=True) ==
                         root.resolve(strict=True))
    except (OSError, ValueError):
        workdir_match = False
    clean = runtime_status == ""
    verified = bool(
        active == "active"
        and workdir_match
        and valid_head
        and valid_unit_sha
        and valid_marker_sha
        and expected_ref in ALLOWED_REFS
        and marker_ref == expected_ref
        and runtime_head == expected_sha == marker_sha
        and marker.get("schema") == "agentos.action-relay-capabilities/v1"
        and clean
        and not pending
    )
    return {
        "schema": SCHEMA,
        "verified_disk_and_unit_generation": verified,
        "service_active": active == "active",
        "unit_workdir_match": workdir_match,
        "unit_source_ref_allowlisted": expected_ref in ALLOWED_REFS,
        "unit_commit_valid": valid_unit_sha,
        "runtime_head_valid": valid_head,
        "marker_commit_valid": valid_marker_sha,
        "unit_marker_runtime_sha_match": bool(valid_head and valid_unit_sha and valid_marker_sha
                                             and runtime_head == expected_sha == marker_sha),
        "unit_marker_source_ref_match": bool(expected_ref in ALLOWED_REFS
                                             and expected_ref == marker_ref),
        "marker_schema_valid": bool(marker and marker.get("schema") ==
                                     "agentos.action-relay-capabilities/v1"),
        "worktree_clean": clean,
        "pending_transaction": pending,
        "observed_runtime_commit": runtime_head if valid_head else None,
        "source_ref_class": expected_ref if expected_ref in ALLOWED_REFS else "unknown",
        "live_process_import_proven": False,
        "production_rollback_proven": False,
        "rescue_channel_proven": False,
    }


def main() -> int:
    active = command("/usr/bin/systemctl", "--user", "show", UNIT, "-p", "ActiveState", "--value")
    workdir = command("/usr/bin/systemctl", "--user", "show", UNIT, "-p", "WorkingDirectory", "--value")
    unit_env = command("/usr/bin/systemctl", "--user", "show", UNIT, "-p", "Environment", "--value")
    head = command("/usr/bin/git", "-C", str(RUNTIME), "rev-parse", "--verify", "HEAD")
    status = command("/usr/bin/git", "-C", str(RUNTIME), "status", "--porcelain", "--untracked-files=all")
    evidence = assess(active=active, workdir=workdir, unit_environment=unit_env,
                      runtime_head=head, runtime_status=status,
                      marker=safe_marker(MARKER), pending=PENDING.exists())
    print(json.dumps(evidence, sort_keys=True, separators=(",", ":")))
    return 0 if evidence["verified_disk_and_unit_generation"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
