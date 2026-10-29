"""Separate Paw publisher CLI; never started by the unprivileged wake worker.

A trusted service manager supplies GH_TOKEN and absolute data roots. This
entrypoint does not merge, deploy or claim independent acceptance.
"""
from __future__ import annotations

import argparse
import contextlib
import fcntl
import json
import os
import sys
from pathlib import Path

from agentos_node.paw_engineering_handoff_publisher import publish_durable_paw_handoff
from agentos_node.paw_engineering_worktree import PawWorktreeBoundaryError


def publish_once(*, runtime_root: Path, workspace_root: Path, generation: int,
                 environment: dict[str, str] | None = None,
                 publication_root: Path | None = None,
                 assignment_id: str = "paw-470-inspection-v1") -> dict:
    env = os.environ if environment is None else environment
    # GH_TOKEN must be injected only into the standalone publisher process.
    # Presence of a token is a prerequisite, not proof of remote permission.
    if not env.get("GH_TOKEN") and not env.get("GITHUB_TOKEN"):
        raise PawWorktreeBoundaryError("paw_publisher_github_identity_missing")
    if not runtime_root.is_absolute() or not workspace_root.is_absolute():
        raise PawWorktreeBoundaryError("paw_publisher_absolute_roots_required")
    receipt = publish_durable_paw_handoff(
        runtime_root=runtime_root, workspace_root=workspace_root,
        generation=generation, authenticated_publisher=True,
        publication_root=publication_root,
        **({"assignment_id": assignment_id} if assignment_id != "paw-470-inspection-v1" else {}),
    )
    return {
        "schema": receipt.schema,
        "status": "published_draft",
        "work_id": receipt.work_id,
        "commit_sha": receipt.commit_sha,
        "pr_number": receipt.pr_number,
        "pr_url": receipt.pr_url,
        "merged": False,
        "independent_acceptance_pass": False,
    }


@contextlib.contextmanager
def _publication_lock(state_root: Path):
    """Serialize all publisher passes; failed runs release the kernel lock."""
    if not state_root.is_dir() or state_root.is_symlink():
        raise PawWorktreeBoundaryError('paw_publisher_runtime_root_invalid')
    lock_path = state_root / '.paw-publisher.lock'
    if lock_path.is_symlink():
        raise PawWorktreeBoundaryError('paw_publisher_lock_invalid')
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise PawWorktreeBoundaryError('paw_publisher_already_running') from exc
        yield
    finally:
        os.close(fd)
def publish_latest(*, runtime_root: Path, workspace_root: Path,
                   environment: dict[str, str] | None = None,
                   publication_root: Path | None = None) -> dict:
    state_root = publication_root if publication_root is not None else runtime_root
    with _publication_lock(state_root):
        return _publish_latest_locked(runtime_root=runtime_root, workspace_root=workspace_root, environment=environment, publication_root=state_root)


def _publish_latest_locked(*, runtime_root: Path, workspace_root: Path,
                           environment: dict[str, str] | None = None,
                           publication_root: Path | None = None) -> dict:
    """One locked reconciler pass; select oldest unpublished handoff."""
    import re
    from agent_core.employee_runtime import EmployeeRuntime
    from agentos_node.paw_engineering_grant import require_dynamic_paw_assignment_binding
    receipt_root = runtime_root / "lifecycle/receipts"
    if not receipt_root.is_dir():
        return {"status": "idle", "reason": "no_receipt"}
    candidates = []
    for directory in sorted(receipt_root.iterdir()):
        if not directory.is_dir() or directory.is_symlink():
            continue
        assignment = directory.name
        if assignment != "paw-470-inspection-v1":
            try:
                require_dynamic_paw_assignment_binding(
                    assignment_id=assignment, runtime=EmployeeRuntime(runtime_root),
                )
            except (OSError, ValueError, KeyError, TypeError, RuntimeError, PermissionError, PawWorktreeBoundaryError):
                continue
        candidates.extend((assignment, p) for p in directory.iterdir()
                          if re.fullmatch(r"[0-9]{6}\.json", p.name))
    if not candidates:
        return {"status": "idle", "reason": "no_receipt"}
    import json
    # Durable publish receipts are separate from immutable employee receipts.
    published = (publication_root if publication_root is not None else runtime_root) / 'paw-publications'
    for assignment_id, path in sorted(candidates, key=lambda item: (item[0], item[1].name)):
        if path.is_symlink():
            raise PawWorktreeBoundaryError('paw_publisher_receipt_symlink')
        try:
            receipt = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, UnicodeError, ValueError) as exc:
            raise PawWorktreeBoundaryError('paw_publisher_receipt_invalid') from exc
        if not isinstance(receipt, dict):
            raise PawWorktreeBoundaryError('paw_publisher_receipt_invalid')
        summary = receipt.get('result_summary')
        if not (receipt.get('outcome') == 'handoff' and isinstance(summary, dict)
                and summary.get('bounded_stage') == 'paw-authorized-local-commit'):
            continue
        # Namespace publication markers by the trusted receipt assignment.
        # Preserve historical A markers for replay compatibility; future B
        # assignments must never alias A's generation-only receipt filename.
        marker = published / (assignment_id + "--" + path.name)
        legacy_marker = published / path.name
        if assignment_id == "paw-470-inspection-v1" and legacy_marker.exists():
            marker = legacy_marker
        if marker.exists():
            if marker.is_symlink():
                raise PawWorktreeBoundaryError('paw_publisher_marker_invalid')
            try:
                record = json.loads(marker.read_text(encoding='utf-8'))
            except (OSError, UnicodeError, ValueError) as exc:
                raise PawWorktreeBoundaryError('paw_publisher_marker_invalid') from exc
            if (not isinstance(record, dict) or record.get('status') != 'published_draft'
                    or record.get('schema') != 'agentos.paw-draft-publication-receipt/v1'
                    or record.get('commit_sha') != summary.get('commit_sha')
                    or record.get('work_id') != summary.get('work_id')
                    or record.get('merged') is not False
                    or record.get('independent_acceptance_pass') is not False
                    or type(record.get('pr_number')) is not int or record['pr_number'] < 1
                    or record.get('pr_url') != (
                        'https://github.com/alston-personal/agentmanager/pull/'
                        + str(record['pr_number'])
                    )):
                raise PawWorktreeBoundaryError('paw_publisher_marker_invalid')
            continue
        generation = int(path.name[:-5])
        result = publish_once(runtime_root=runtime_root, workspace_root=workspace_root,
                              generation=generation, environment=environment,
                              publication_root=publication_root,
                              **({"assignment_id": assignment_id} if assignment_id != "paw-470-inspection-v1" else {}))
        if result.get('status') != 'published_draft' or result.get('commit_sha') != summary.get('commit_sha'):
            raise PawWorktreeBoundaryError('paw_publisher_remote_receipt_mismatch')
        published.mkdir(parents=True, exist_ok=True)
        tmp = published / (assignment_id + '--' + path.name + '.tmp')
        # An interrupted write may leave an incomplete temporary receipt.
        # The remote publication has already been reverified by publish_once.
        # Under the exclusive publisher lock, never trust or reuse the stale tmp.
        if tmp.is_symlink():
            raise PawWorktreeBoundaryError('paw_publisher_marker_tmp_invalid')
        if tmp.exists():
            if not tmp.is_file():
                raise PawWorktreeBoundaryError('paw_publisher_marker_tmp_invalid')
            tmp.unlink()
        with tmp.open('x', encoding='utf-8') as handle:
            json.dump(result, handle, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, marker)
        return result
    return {'status': 'idle', 'reason': 'no_engineering_handoff'}

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Publish verified Paw handoff as Draft PR")
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--workspace-root", type=Path, required=True)
    parser.add_argument("--generation", type=int)
    parser.add_argument("--latest", action="store_true")
    parser.add_argument("--publication-root", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.latest:
            result = publish_latest(runtime_root=args.runtime_root, workspace_root=args.workspace_root, publication_root=args.publication_root)
        elif args.generation is not None:
            result = publish_once(runtime_root=args.runtime_root, workspace_root=args.workspace_root, generation=args.generation, publication_root=args.publication_root)
        else:
            raise PawWorktreeBoundaryError("paw_publisher_generation_required")
    except (PawWorktreeBoundaryError, OSError, ValueError):
        print(json.dumps({"status": "blocked", "error_code": "paw_publisher_not_ready"}))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
