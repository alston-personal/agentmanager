#!/usr/bin/env python3
"""Fail when AgentOS architecture evolves without its authoritative docs.

This guard intentionally checks two things:
1. Static reality: canonical entry-point docs and their claimed core paths exist.
2. Change-set coupling: architecture-sensitive implementation changes must update
   at least one authoritative current-state document in the same change set.

It does not try to prove that prose is semantically perfect. It makes silent
implementation/documentation divergence a CI-visible regression instead of a
maintenance task someone has to remember months later.
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
}

# Claims made by docs/CURRENT_STATE.md that must remain tied to real repository paths.
REQUIRED_REALITY_PATHS = (
    "agent_core/control_plane.py",
    "agent_core/session_lifecycle.py",
    "agent_core/governance_directory.py",
    "agent_core/resource_registry.py",
    "agent_core/realm_fabric.py",
    "runtime_core/interfaces.py",
    "scripts/continuation_state.py",
    "scripts/agentos_node.py",
    "scripts/drift_guard.py",
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


def coupling_errors(base: str | None) -> list[str]:
    if not base:
        return []
    changed = changed_files(base)
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
        "architecture-sensitive implementation changed without an authoritative documentation update: "
        + sample
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="Detect AgentOS implementation/documentation drift")
    parser.add_argument(
        "--base",
        help="base commit/ref for change-set coupling check (omit for static-only local check)",
    )
    args = parser.parse_args()

    errors = static_errors() + coupling_errors(args.base)
    if errors:
        print("Documentation Reality Guard: FAIL")
        for error in errors:
            print(f"ERROR: {error}")
        print("\nUpdate README.md, ONBOARDING.md, AGENTS.md, or docs/CURRENT_STATE.md to reflect the new architecture.")
        return 1

    print("Documentation Reality Guard: PASS")
    if args.base:
        print(f"base={args.base}")
    print("authoritative_docs=" + ",".join(sorted(AUTHORITATIVE_DOCS)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
