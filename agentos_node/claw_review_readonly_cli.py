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
    return {
        "commit_sha": commit_sha,
        "manifest_sha256": hashlib.sha256(manifest).hexdigest(),
        "patch_sha256": hashlib.sha256(patch).hexdigest(),
        "patch_bytes": len(patch),
        "changed_entries": len(manifest.splitlines()),
        "independent_review_verdict": "NOT_REVIEWED",
    }


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
    args = parser.parse_args(argv)
    if args.presence_generation < 1 or not args.wake_id.strip() or not args.node_id.strip():
        parser.error("invalid_exact_claw_wake")
    if bool(args.inspect_commit) != bool(args.repository):
        parser.error("claw_repository_and_commit_required_together")
    if args.inspect_commit:
        # Evidence-only mode; intentionally never writes lifecycle receipts or
        # turns observation into a Claw PASS. Host dispatch does not supply these
        # options, so a wake alone cannot self-authorize Git inspection.
        try:
            evidence = inspect_local_commit(args.repository, args.inspect_commit)
        except (ValueError, OSError, subprocess.CalledProcessError,
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
