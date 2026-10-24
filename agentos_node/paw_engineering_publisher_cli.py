"""Separate Paw publisher CLI; never started by the unprivileged wake worker.

A trusted service manager supplies GH_TOKEN and absolute data roots. This
entrypoint does not merge, deploy or claim independent acceptance.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from agentos_node.paw_engineering_handoff_publisher import publish_durable_paw_handoff
from agentos_node.paw_engineering_worktree import PawWorktreeBoundaryError


def publish_once(*, runtime_root: Path, workspace_root: Path, generation: int,
                 environment: dict[str, str] | None = None) -> dict:
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Publish verified Paw handoff as Draft PR")
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--workspace-root", type=Path, required=True)
    parser.add_argument("--generation", type=int, required=True)
    args = parser.parse_args(argv)
    try:
        result = publish_once(
            runtime_root=args.runtime_root,
            workspace_root=args.workspace_root,
            generation=args.generation,
        )
    except (PawWorktreeBoundaryError, OSError, ValueError):
        print(json.dumps({"status": "blocked", "error_code": "paw_publisher_not_ready"}))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
