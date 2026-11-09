#!/usr/bin/env python3
"""Fail when AgentOS architecture evolves without its authoritative docs.

This guard intentionally checks:
1. Static reality: canonical entry-point docs and their claimed core paths exist.
2. Change-set coupling: architecture-sensitive implementation changes must update
   at least one authoritative current-state document in the same change set.
   Supports --base <ref>, --staged (pre-commit), and --worktree (active development/Claw).

It makes silent implementation/documentation divergence a visible regression
during development, before commit, and in CI.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent

AUTHORITATIVE_DOCS = {
    "README.md",
    "ONBOARDING.md",
    "AGENTS.md",
    "docs/CURRENT_STATE.md",
}

# Changes under these surfaces can materially alter the public AgentOS mental model.
ARCHITECTURE_PREFIXES = (
    "agent_core/",
    "runtime_core/",
    ".agent/roles/",
    ".agent/governance/",
    ".agentos/commands/",
)
ARCHITECTURE_FILES = {
    ".agent/CONSTITUTION.yaml",
    "scripts/continuation_state.py",
    "scripts/agentos_node.py",
    "scripts/drift_guard.py",
    "scripts/platform_runtime.py",
    "scripts/rhea_role_steward.py",
}

# Claims made by docs/CURRENT_STATE.md that must remain tied to real repository paths.
REQUIRED_REALITY_PATHS = (
    "agent_core/control_plane.py",
    "agent_core/session_lifecycle.py",
    "agent_core/governance_directory.py",
    "agent_core/resource_registry.py",
    "agent_core/realm_fabric.py",
    "agent_core/role_seal.py",
    "runtime_core/interfaces.py",
    "scripts/continuation_state.py",
    "scripts/agentos_node.py",
    "scripts/drift_guard.py",
    "scripts/rhea_role_steward.py",
    "tests/test_continuation_state.py",
    "tests/test_control_plane.py",
    "tests/test_governance_directory.py",
    "tests/test_resource_registry.py",
    "docs/AGENTOS_NODE.md",
)


def git(*args: str) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or f"git {' '.join(args)} failed")
    return proc.stdout


def changed_files(base: str) -> set[str]:
    # PRs normally want merge-base semantics. Fall back to two-dot for shallow/local cases.
    try:
        output = git("diff", "--name-only", f"{base}...HEAD")
    except RuntimeError:
        output = git("diff", "--name-only", f"{base}..HEAD")
    return {line.strip() for line in output.splitlines() if line.strip()}


def staged_files() -> set[str]:
    output = git("diff", "--cached", "--name-only")
    return {line.strip() for line in output.splitlines() if line.strip()}


def worktree_files() -> set[str]:
    try:
        output = git("diff", "HEAD", "--name-only")
    except RuntimeError:
        output = git("diff", "--name-only")
    return {line.strip() for line in output.splitlines() if line.strip()}


def is_architecture_path(path: str) -> bool:
    return path in ARCHITECTURE_FILES or path.startswith(ARCHITECTURE_PREFIXES)


def static_errors() -> list[str]:
    errors: list[str] = []
    for doc in AUTHORITATIVE_DOCS:
        if not (ROOT / doc).is_file():
            errors.append(f"authoritative document missing: {doc}")

    for path in REQUIRED_REALITY_PATHS:
        if not (ROOT / path).exists():
            errors.append(f"CURRENT_STATE implementation claim has no repository path: {path}")

    readme = (ROOT / "README.md").read_text(encoding="utf-8") if (ROOT / "README.md").exists() else ""
    current = (ROOT / "docs/CURRENT_STATE.md").read_text(encoding="utf-8") if (ROOT / "docs/CURRENT_STATE.md").exists() else ""

    if "docs/CURRENT_STATE.md" not in readme:
        errors.append("README.md must link to docs/CURRENT_STATE.md")
    if "Switch models. Switch machines. Continue the same work." not in readme:
        errors.append("README.md lost the current continuity product statement")
    for marker in ("Implemented", "Verified", "Research", "Cognitive IR"):
        if marker not in current:
            errors.append(f"docs/CURRENT_STATE.md missing reality marker: {marker}")

    return errors


def verify_file_set_coupling(changed: set[str], context_name: str) -> list[str]:
    architecture = sorted(path for path in changed if is_architecture_path(path))
    if not architecture:
        return []
    doc_changes = sorted(changed & AUTHORITATIVE_DOCS)
    if doc_changes:
        return []
    sample = ", ".join(architecture[:8])
    if len(architecture) > 8:
        sample += f", ... (+{len(architecture) - 8})"
    return [
        f"[{context_name}] architecture-sensitive implementation changed without an authoritative documentation update: "
        + sample
    ]


def coupling_errors(base: str | None, staged: bool = False, worktree: bool = False) -> list[str]:
    errors: list[str] = []
    if base:
        errors.extend(verify_file_set_coupling(changed_files(base), f"base={base}"))
    if staged:
        errors.extend(verify_file_set_coupling(staged_files(), "pre-commit staged"))
    if worktree:
        errors.extend(verify_file_set_coupling(worktree_files(), "active worktree"))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Detect AgentOS implementation/documentation drift")
    parser.add_argument(
        "--base",
        help="base commit/ref for change-set coupling check",
    )
    parser.add_argument(
        "--staged",
        action="store_true",
        help="check git staged files (used by git pre-commit hook)",
    )
    parser.add_argument(
        "--worktree",
        action="store_true",
        help="check active uncommitted worktree changes (used by Claw auditor / active development)",
    )
    args = parser.parse_args()

    errors = static_errors() + coupling_errors(args.base, staged=args.staged, worktree=args.worktree)
    if errors:
        print("Documentation Reality Guard: FAIL")
        for error in errors:
            print(f"ERROR: {error}")
        print("\nUpdate README.md, ONBOARDING.md, AGENTS.md, or docs/CURRENT_STATE.md to reflect the new architecture.")
        return 1

    print("Documentation Reality Guard: PASS")
    if args.base:
        print(f"base={args.base}")
    if args.staged:
        print("mode=staged")
    if args.worktree:
        print("mode=worktree")
    print("authoritative_docs=" + ",".join(sorted(AUTHORITATIVE_DOCS)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
