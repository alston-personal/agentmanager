#!/usr/bin/env python3
"""Fail-closed, evidence-based preflight for high-risk AgentOS engineering PRs.

This is a CI/documentation admission check, NOT deployment/ONE authorization.
Evidence can be falsely asserted; independent reviewers and live receipts remain
mandatory before privileged changes.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any

SCHEMA = "agentos.systemic-change-preflight/v1"
HIGH_RISK_PREFIXES = (
    "agent_core/", "agentos_node/", ".github/workflows/",
    "governance/", ".agent/governance/", ".agent/CONSTITUTION.yaml",
)
HIGH_RISK_NAMES = {"AGENTS.md"}
EVIDENCE_ROOT = Path("docs/governance/change-preflights")


def classify(paths: list[str]) -> str:
    """Documentation-only, test-only and isolated product work stay lightweight."""
    return "high" if any(
        p in HIGH_RISK_NAMES or p.startswith(HIGH_RISK_PREFIXES)
        for p in paths
    ) else "standard"


def validate_manifest(payload: Any, changed_files: list[str]) -> list[str]:
    errors: list[str] = []
    if not isinstance(payload, dict) or payload.get("schema") != SCHEMA:
        return ["invalid_preflight_schema"]
    if classify(changed_files) != "high":
        return []
    for field in (
        "change_id", "goal", "scope_inventory", "existing_capabilities",
        "authority_map", "failure_modes", "implementation_plan",
        "verification_plan", "rollback_plan", "unknowns", "reviewers",
    ):
        value = payload.get(field)
        if field in ("change_id", "goal"):
            if not isinstance(value, str) or not value.strip():
                errors.append("missing_" + field)
        elif not isinstance(value, list) or not value:
            errors.append("missing_" + field)
        elif any(not isinstance(x, str) or not x.strip() for x in value):
            errors.append("invalid_" + field)
    if payload.get("risk_tier") != "high":
        errors.append("invalid_risk_tier")
    if payload.get("phase") not in ("inventory", "design", "implementation", "acceptance"):
        errors.append("invalid_phase")
    if payload.get("status") not in ("proposed", "in-progress", "verified"):
        errors.append("invalid_status")
    # Each high-risk change must declare its bounded impact and evidence links.
    evidence = payload.get("evidence_refs")
    if not isinstance(evidence, list) or not evidence or any(
        not isinstance(x, str) or not x.strip() for x in evidence
    ):
        errors.append("missing_evidence_refs")
    if payload.get("ready_for_implementation") is True:
        if payload.get("phase") not in ("implementation", "acceptance"):
            errors.append("invalid_implementation_phase")
        if payload.get("review_status") != "reviewed":
            errors.append("review_not_recorded")
        if any("unknown" == str(x).strip().lower() for x in payload.get("authority_map", []) if isinstance(x,str)):
            errors.append("unresolved_authority")
    elif payload.get("ready_for_implementation") is not False:
        errors.append("invalid_implementation_readiness")
    return errors


def changed_paths(base: str) -> list[str]:
    if not re.fullmatch(r"[A-Za-z0-9_./-]+", base):
        raise ValueError("invalid_base")
    result = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=ACMR", f"{base}...HEAD"],
        capture_output=True, text=True, check=True,
    )
    return [p for p in result.stdout.splitlines() if p]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="origin/main")
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    files = changed_paths(args.base)
    if classify(files) == "standard":
        print(json.dumps({"result": "PASS", "risk": "standard", "files": len(files)}))
        return 0
    # A PR must introduce or update its own record; old plans cannot bless new work.
    submitted = {Path(p) for p in files}
    manifests = [args.manifest] if args.manifest else sorted(
        p for p in submitted if p.parent == EVIDENCE_ROOT and p.suffix == ".json"
    )
    failures: list[str] = []
    valid: list[str] = []
    for path in manifests:
        if not path or not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            failures.append(f"{path}: unreadable_manifest")
            continue
        errors = validate_manifest(data, files)
        if errors:
            failures.append(f"{path}: {','.join(errors)}")
        else:
            valid.append(str(path))
    # A plan is not authorization to start implementation. Policy bootstrap
    # can be proposed as design, but actual code/workflow changes must record
    # review readiness. Human approval is separately enforced by branch rules.
    policy_bootstrap_paths = {
        "AGENTS.md", ".github/workflows/systemic-engineering-preflight.yml",
    }
    requires_readiness = any(
        p.startswith(("agent_core/", "agentos_node/", "governance/", ".agent/governance/"))
        or (p.startswith(".github/workflows/") and p not in policy_bootstrap_paths)
        for p in files
    )
    if requires_readiness:
        reviewed = []
        for p in valid:
            data = json.loads(Path(p).read_text(encoding="utf-8"))
            if data.get("ready_for_implementation") is True and data.get("review_status") == "reviewed":
                reviewed.append(p)
        valid = reviewed
        if not valid:
            failures.append("implementation_requires_reviewed_preflight")
    if not valid:
        print(json.dumps({
            "result": "FAIL", "risk": "high", "reason": "preflight_manifest_required",
            "failures": failures, "changed_files": files,
        }, ensure_ascii=False))
        return 1
    print(json.dumps({
        "result": "PASS", "risk": "high", "manifests": valid, "files": len(files),
        "warning": "record presence does not authenticate approval or deployment authority",
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
