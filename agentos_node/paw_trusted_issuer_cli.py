"""Independent, explicitly approved Paw grant issuer entrypoint.

The issuer reads a private, owner-approved immutable request. It is not called by
Paw, the wake capsule, or the worker's delivery module. It signs only a live,
canonically authorized lease and writes to an issuer-owned private outbox.
A separate privileged delivery service must transport the signed envelope.
"""
from __future__ import annotations

import argparse
import json
import os
import stat
from pathlib import Path

from agent_core.employee_runtime import EmployeeRuntime
from agent_core.employee_lifecycle import EmployeeLifecycle
from agentos_node.paw_engineering_request import issue_and_publish_trusted_paw_public_request
from agentos_node.paw_engineering_worktree import PawWorktreeBoundaryError


def _private_regular(path: Path, *, expected_uid: int) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise PawWorktreeBoundaryError("paw_issuer_private_input_missing")
    info = path.stat()
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != expected_uid
            or info.st_mode & 0o077 or info.st_nlink != 1):
        raise PawWorktreeBoundaryError("paw_issuer_private_input_untrusted")
    return path.read_bytes()


def issue_approved_once(*, approval_path: Path, private_key_path: Path,
                        issuer_outbox: Path, runtime_root: Path,
                        registry_path: Path) -> Path:
    """Fail closed on missing signed-off approval or non-current lease."""
    uid = os.geteuid()
    approval = json.loads(_private_regular(Path(approval_path), expected_uid=uid))
    if not isinstance(approval, dict) or set(approval) != {
        "schema", "assignment_id", "lease_id", "wake_id", "presence_generation",
        "lease_generation", "grant", "expected_sha256", "replacement",
    } or approval["schema"] != "agentos.paw-owner-approved-issuer-request/v1":
        raise PawWorktreeBoundaryError("paw_issuer_approval_shape_invalid")
    private_key = _private_regular(Path(private_key_path), expected_uid=uid)
    if len(private_key) != 32:
        raise PawWorktreeBoundaryError("paw_issuer_private_key_invalid")
    runtime = EmployeeRuntime(runtime_root)
    lifecycle = EmployeeLifecycle(runtime)
    return issue_and_publish_trusted_paw_public_request(
        authority_dir=issuer_outbox, assignment_id=approval["assignment_id"],
        grant=approval["grant"], expected_sha256=approval["expected_sha256"],
        replacement=approval["replacement"], issuer_private_key=private_key,
        trusted_wake_id=approval["wake_id"],
        trusted_presence_generation=approval["presence_generation"],
        trusted_lease_generation=approval["lease_generation"],
        trusted_lease_id=approval["lease_id"], lifecycle=lifecycle,
        registry_path=registry_path, trusted_runtime=runtime,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Issue one independently approved Paw request")
    parser.add_argument("--approval", type=Path, required=True)
    parser.add_argument("--private-key", type=Path, required=True)
    parser.add_argument("--issuer-outbox", type=Path, required=True)
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--registry-path", type=Path, required=True)
    args = parser.parse_args(argv)
    issue_approved_once(
        approval_path=args.approval, private_key_path=args.private_key,
        issuer_outbox=args.issuer_outbox, runtime_root=args.runtime_root,
        registry_path=args.registry_path,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
