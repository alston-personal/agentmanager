"""Bounded offline Claw evidence reader. No verdict or lifecycle authority."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

SCHEMA = "agentos.claw-review-readonly-worker-cli-result/v1"
SHA = re.compile(r"^[0-9a-f]{40}$")


def _absolute(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise argparse.ArgumentTypeError("claw_worker_path_must_be_absolute")
    return path.resolve()


def inspect_local_commit(repository: Path, commit_sha: str) -> dict[str, object]:
    """Read only an existing local Git object; reject symlinks and external commands."""
    if not SHA.fullmatch(commit_sha):
        raise ValueError("claw_commit_sha_invalid")
    if not repository.is_dir() or repository.is_symlink():
        raise ValueError("claw_repository_invalid")
    def git(*arguments: str) -> bytes:
        result = subprocess.run(
            ["git", "-C", str(repository), "--no-optional-locks",
             "-c", "core.hooksPath=/dev/null", *arguments],
            check=True, capture_output=True, timeout=15,
            env={"PATH": "/usr/bin:/bin", "HOME": "/nonexistent",
                 "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null",
                 "GIT_OPTIONAL_LOCKS": "0", "GIT_NO_REPLACE_OBJECTS": "1",
                 "GIT_NO_LAZY_FETCH": "1", "GIT_TERMINAL_PROMPT": "0"},
        )
        return result.stdout
    try:
        actual = git("rev-parse", "--verify", commit_sha + "^{commit}").strip().decode("ascii")
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise ValueError("claw_commit_not_available_locally") from exc
    if actual != commit_sha:
        raise ValueError("claw_commit_identity_mismatch")
    manifest = git("diff-tree", "--root", "--no-commit-id", "--name-status", "-r", "--no-renames", commit_sha)
    # A filename manifest is not sufficient review evidence. Bind the exact
    # patch bytes too, with a strict size ceiling. Never infer PASS from it.
    patch = git("show", "--format=", "--no-ext-diff", "--no-renames",
                "--root", "--binary", commit_sha)
    if len(patch) > 2_000_000:
        raise ValueError("claw_patch_exceeds_bounded_review")
    # A deterministic reviewer can report a concrete blocking defect without
    # pretending that a clean whitespace check constitutes full approval.
    # git show --check exits nonzero for whitespace errors but must not be
    # allowed to execute external diff drivers.
    check = subprocess.run(
        ["git", "-C", str(repository), "--no-optional-locks",
         "-c", "core.hooksPath=/dev/null",
         "show", "--check", "--format=", "--no-ext-diff", commit_sha],
        capture_output=True, timeout=15,
        env={"PATH": "/usr/bin:/bin", "HOME": "/nonexistent",
             "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null",
             "GIT_OPTIONAL_LOCKS": "0", "GIT_NO_REPLACE_OBJECTS": "1",
             "GIT_NO_LAZY_FETCH": "1", "GIT_TERMINAL_PROMPT": "0"},
    )
    if check.returncode not in {0, 2}:
        raise ValueError("claw_static_check_unavailable")
    static_result = "FAIL" if check.returncode == 2 else "NO_FINDINGS"
    return {
        "commit_sha": commit_sha,
        "manifest_sha256": hashlib.sha256(manifest).hexdigest(),
        "patch_sha256": hashlib.sha256(patch).hexdigest(),
        "patch_bytes": len(patch),
        "changed_entries": len(manifest.splitlines()),
        "independent_review_verdict": "NOT_REVIEWED",
        "static_check": static_result,
        "static_diagnostic_sha256": hashlib.sha256(check.stdout + check.stderr).hexdigest(),
    }


def inspect_governed_review_target(runtime_root: Path, repository: Path, work_item_id: str) -> dict[str, object]:
    """Resolve the exact target from canonical WorkItem and Paw terminal receipt.

    Wake metadata cannot select a repository, commit, or review result.
    This is evidence collection only and does not issue a PASS.
    """
    from agent_core.core_work_items import WorkItemStore
    from agent_core.employee_runtime import EmployeeRuntime
    from agent_core.employee_lifecycle import EmployeeLifecycle

    runtime = EmployeeRuntime(runtime_root)
    item = WorkItemStore(runtime).get(work_item_id)
    if "independent_review_required" not in item.authority_requirements:
        raise PermissionError("claw_review_not_required")
    assignment = runtime.get_assignment(item.assignment_id)
    if assignment.employee_id != item.employee_id or assignment.state not in {"completed", "handoff"}:
        raise PermissionError("claw_author_not_completed")
    result = assignment.result
    if not isinstance(result, dict):
        raise PermissionError("claw_author_receipt_missing")
    generation = result.get("generation")
    if type(generation) is not int or generation < 1:
        raise PermissionError("claw_author_generation_invalid")
    lifecycle = EmployeeLifecycle(runtime)
    path = lifecycle._receipt_path(item.assignment_id, generation)
    lease = lifecycle.get_lease(item.assignment_id)
    if (not lease or lease.generation != generation or lease.status != assignment.state
            or result.get("receipt") != str(path.relative_to(runtime.root))
            or result.get("schema") != "agentos.employee-assignment-receipt/v1"):
        raise PermissionError("claw_author_receipt_unverified")
    receipt = json.loads(path.read_text(encoding="utf-8"))
    summary = receipt.get("result_summary")
    if (receipt.get("assignment_id") != item.assignment_id
            or receipt.get("employee_id") != item.employee_id
            or receipt.get("lease_id") != lease.lease_id
            or receipt.get("generation") != generation
            or receipt.get("outcome") != assignment.state
            or not isinstance(summary, dict)):
        raise PermissionError("claw_author_receipt_unverified")
    sha = summary.get("commit_sha")
    if not isinstance(sha, str) or not SHA.fullmatch(sha):
        raise PermissionError("claw_author_commit_not_pinned")
    evidence = inspect_local_commit(repository, sha)
    return {"work_item_id": item.work_item_id, "assignment_id": item.assignment_id,
            "assignment_generation": generation, **evidence}

def finish_governed_claw_blocker(
    runtime_root: Path, work_item_id: str, *, wake_id: str,
    presence_generation: int, evidence: dict[str, object],
) -> dict[str, object]:
    """Write an honest blocked lifecycle receipt, never an independent verdict.

    Only an already projected, separately owned Claw assignment can finish.
    An S4 delivered wake is required before claim; a local capsule is insufficient.
    """
    from agent_core.employee_lifecycle import EmployeeLifecycle
    from agent_core.employee_runtime import EmployeeRuntime
    from agent_core.core_work_items import WorkItemStore
    from agentos_node.product_employee_worker import _governed_delivery_index

    runtime = EmployeeRuntime(runtime_root)
    work = WorkItemStore(runtime).get(work_item_id)
    review_id = "claw-review-" + work_item_id
    review = runtime.get_assignment(review_id)
    reviewer = runtime.get_employee(review.employee_id)
    if (review.employee_id == work.employee_id
            or "sector.claw" not in reviewer.role_ids
            or "security.audit" not in reviewer.skill_ids
            or review.state != "pending"):
        raise PermissionError("claw_review_independence_or_state_invalid")
    # Require the immutable ONE delivery ledger for this exact pending assignment.
    deliveries = [
        x for group in _governed_delivery_index(runtime_root).values()
        for x in group
        if x.get("employee_id") == review.employee_id
        and x.get("assignment_id") == review_id
        and x.get("wake_id") == wake_id
        and x.get("presence_generation") == presence_generation
    ]
    if len(deliveries) != 1:
        raise PermissionError("claw_review_governed_delivery_missing")
    lifecycle = EmployeeLifecycle(runtime)
    lease_id = f"claw-review-{wake_id}-p{presence_generation}"
    lease = lifecycle.claim(review_id, review.employee_id, lease_id)
    summary = {
        "schema": "agentos.claw-review-blocker/v1",
        "target_assignment_id": work.assignment_id,
        "target_generation": evidence["assignment_generation"],
        "commit_sha": evidence["commit_sha"],
        "patch_sha256": evidence["patch_sha256"],
        "reason": "independent_review_executor_unavailable",
        "verdict": "NOT_REVIEWED",
    }
    receipt = lifecycle.finish(review_id, lease_id, state="blocked", result_summary=summary)
    return {"assignment_id": review_id, "generation": lease.generation,
            "receipt_outcome": receipt.outcome, "verdict": "NOT_REVIEWED"}

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="claw-review-readonly")
    parser.add_argument("--runtime-root", type=_absolute, required=True)
    parser.add_argument("--wake-root", type=_absolute, required=True)
    parser.add_argument("--worker-state-root", type=_absolute, required=True)
    parser.add_argument("--node-id", required=True)
    parser.add_argument("--wake-id", required=True)
    parser.add_argument("--presence-generation", type=int, required=True)
    parser.add_argument("--once", action="store_true", required=True)
    parser.add_argument("--inspect-commit", help="Exact pinned SHA for evidence-only inspection")
    parser.add_argument("--repository", type=_absolute, help="Explicit local repository for evidence-only inspection")
    parser.add_argument("--work-item-id", help="Resolve pinned commit from canonical Paw receipt")
    args = parser.parse_args(argv)
    if args.presence_generation < 1 or not args.wake_id.strip() or not args.node_id.strip():
        parser.error("invalid_exact_claw_wake")
    if args.work_item_id and args.inspect_commit:
        parser.error("claw_review_target_modes_mutually_exclusive")
    if bool(args.inspect_commit or args.work_item_id) != bool(args.repository):
        parser.error("claw_repository_and_target_required_together")
    if args.inspect_commit or args.work_item_id:
        # Evidence-only mode; intentionally never writes lifecycle receipts or
        # turns observation into a Claw PASS. Host dispatch does not supply these
        # options, so a wake alone cannot self-authorize Git inspection.
        try:
            evidence = (inspect_governed_review_target(args.runtime_root, args.repository, args.work_item_id)
                        if args.work_item_id else inspect_local_commit(args.repository, args.inspect_commit))
        except (ValueError, PermissionError, KeyError, OSError, subprocess.CalledProcessError,
                subprocess.TimeoutExpired):
            print(json.dumps({"schema": SCHEMA, "status": "blocked",
                              "work_performed": False,
                              "error_code": "claw_commit_evidence_unavailable",
                              "credential_exposed": False,
                              "session_identity_exposed": False,
                              "verified_marker_emitted": False}, sort_keys=True))
            return 2
        print(json.dumps({"schema": SCHEMA, "status": "blocked",
                          "work_performed": True,
                          "error_code": "claw_review_not_performed",
                          "evidence": evidence,
                          "credential_exposed": False,
                          "session_identity_exposed": False,
                          "verified_marker_emitted": False}, sort_keys=True))
        return 2
    print(json.dumps({
        "schema": SCHEMA, "status": "blocked", "work_performed": False,
        "error_code": "claw_independent_review_executor_unavailable",
        "credential_exposed": False, "session_identity_exposed": False,
        "verified_marker_emitted": False,
    }, sort_keys=True))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
