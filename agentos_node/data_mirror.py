#!/usr/bin/env python3
"""AgentOS Edge Node Read-Only Data Mirror Enforcement (GOV-2026-11-20-001).

Implements the constitutional principle `edge_node_readonly_data_mirror`:
- Every AgentOS edge node maintains a local read-only mirror of `agent-data`.
- Local push is physically disabled via `git remote set-url --push origin DISABLED_READ_ONLY_MIRROR`.
- Periodic synchronization uses one-way `git fetch` + `git reset --hard origin/<branch>`.
- All mutations MUST be written remotely via `agentos-one` MCP or Control Plane APIs.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

READONLY_PUSH_SENTINEL = "DISABLED_READ_ONLY_MIRROR"


def _run_git(mirror_dir: Path, args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(mirror_dir),
        capture_output=True,
        text=True,
        check=check,
    )


def get_push_url(mirror_dir: Path, remote: str = "origin") -> str:
    res = _run_git(mirror_dir, ["remote", "get-url", "--push", remote], check=False)
    if res.returncode != 0:
        return ""
    return res.stdout.strip()


def ensure_readonly_push_lock(mirror_dir: Path, remote: str = "origin") -> dict[str, Any]:
    """Physically lock the local mirror so `git push` is impossible."""
    mirror_path = Path(mirror_dir)
    if not (mirror_path / ".git").exists():
        return {
            "ok": False,
            "error": f"not_a_git_repository: {mirror_path}",
            "push_url": "",
            "locked": False,
        }

    _run_git(mirror_path, ["remote", "set-url", "--push", remote, READONLY_PUSH_SENTINEL])
    actual = get_push_url(mirror_path, remote=remote)
    locked = actual == READONLY_PUSH_SENTINEL
    return {
        "ok": locked,
        "mirror_dir": str(mirror_path),
        "remote": remote,
        "push_url": actual,
        "locked": locked,
    }


def verify_readonly_mirror(mirror_dir: Path, remote: str = "origin") -> dict[str, Any]:
    """Audit whether an edge node's `agent-data` mirror obeys GOV-2026-11-20-001."""
    mirror_path = Path(mirror_dir)
    if not (mirror_path / ".git").exists():
        return {
            "compliant": False,
            "reason": "missing_git_mirror",
            "mirror_dir": str(mirror_path),
        }

    push_url = get_push_url(mirror_path, remote=remote)
    if push_url != READONLY_PUSH_SENTINEL:
        return {
            "compliant": False,
            "reason": "push_not_disabled",
            "mirror_dir": str(mirror_path),
            "push_url": push_url,
            "expected_push_url": READONLY_PUSH_SENTINEL,
        }

    status_res = _run_git(mirror_path, ["status", "--porcelain"], check=False)
    dirty = bool(status_res.stdout.strip())
    return {
        "compliant": not dirty,
        "reason": "ok" if not dirty else "dirty_working_tree",
        "mirror_dir": str(mirror_path),
        "push_url": push_url,
        "dirty": dirty,
    }


def sync_readonly_mirror(
    mirror_dir: Path,
    *,
    remote: str = "origin",
    branch: str = "main",
) -> dict[str, Any]:
    """Enforce read-only push lock and perform one-way fetch + hard reset."""
    mirror_path = Path(mirror_dir)
    lock_res = ensure_readonly_push_lock(mirror_path, remote=remote)
    if not lock_res["ok"]:
        return {"ok": False, "stage": "lock", "details": lock_res}

    fetch_res = _run_git(mirror_path, ["fetch", remote, branch], check=False)
    if fetch_res.returncode != 0:
        return {
            "ok": False,
            "stage": "fetch",
            "stderr": fetch_res.stderr.strip(),
            "mirror_dir": str(mirror_path),
        }

    reset_res = _run_git(mirror_path, ["reset", "--hard", f"{remote}/{branch}"], check=False)
    if reset_res.returncode != 0:
        return {
            "ok": False,
            "stage": "reset",
            "stderr": reset_res.stderr.strip(),
            "mirror_dir": str(mirror_path),
        }

    head_res = _run_git(mirror_path, ["rev-parse", "HEAD"], check=False)
    return {
        "ok": True,
        "mirror_dir": str(mirror_path),
        "remote": remote,
        "branch": branch,
        "head": head_res.stdout.strip(),
        "push_locked": True,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AgentOS Edge Node Read-Only Data Mirror Manager")
    parser.add_argument("action", choices=["lock", "verify", "sync"])
    parser.add_argument("--mirror-dir", required=True, help="Local path to agent-data read-only mirror")
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--branch", default="main")
    args = parser.parse_args(argv)

    mirror_path = Path(args.mirror_dir)
    if args.action == "lock":
        res = ensure_readonly_push_lock(mirror_path, remote=args.remote)
        ok = bool(res.get("ok"))
    elif args.action == "verify":
        res = verify_readonly_mirror(mirror_path, remote=args.remote)
        ok = bool(res.get("compliant"))
    else:
        res = sync_readonly_mirror(mirror_path, remote=args.remote, branch=args.branch)
        ok = bool(res.get("ok"))

    print(json.dumps(res, indent=2, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
