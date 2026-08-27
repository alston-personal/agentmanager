#!/usr/bin/env python3
"""AgentOS protected-branch authority guard.

This module encodes one governance invariant: possessing a technical capability
(e.g. a GitHub merge tool) never implies authority to mutate a protected branch.
Agents must stop at READY_FOR_MERGE until an explicit human approval event is
present.  The module is deliberately transport-neutral so GitHub/MCP/CLI
adapters can call the same decision function before a destructive mutation.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, asdict
from fnmatch import fnmatch
import json
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / ".agent" / "governance" / "protected_branches.yaml"


@dataclass(frozen=True)
class AuthorityDecision:
    allowed: bool
    state: str
    reason: str
    branch: str
    protected: bool
    requires_human_approval: bool


def load_policy(path: Path = POLICY) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError("protected branch policy must be an object")
    return data


def branch_rule(branch: str, policy: dict[str, Any]) -> dict[str, Any] | None:
    for rule in policy.get("protected_branches", []) or []:
        if isinstance(rule, dict) and fnmatch(branch, str(rule.get("pattern", ""))):
            return rule
    return None


def authorize(
    *,
    branch: str,
    actor_kind: str,
    explicit_human_approval: bool,
    via_pull_request: bool,
    policy: dict[str, Any] | None = None,
) -> AuthorityDecision:
    policy = policy or load_policy()
    rule = branch_rule(branch, policy)
    if rule is None:
        return AuthorityDecision(
            allowed=True,
            state="ALLOW",
            reason="branch is not protected by AgentOS policy",
            branch=branch,
            protected=False,
            requires_human_approval=False,
        )

    if bool(rule.get("require_pull_request", False)) and not via_pull_request:
        return AuthorityDecision(
            allowed=False,
            state="DENY",
            reason="protected branch mutation must go through a pull request",
            branch=branch,
            protected=True,
            requires_human_approval=bool(rule.get("require_explicit_human_approval", False)),
        )

    requires_human = bool(rule.get("require_explicit_human_approval", False))
    if actor_kind != "human":
        if requires_human and not explicit_human_approval:
            return AuthorityDecision(
                allowed=False,
                state="AWAITING_HUMAN_APPROVAL",
                reason="technical mergeability is not governance authority",
                branch=branch,
                protected=True,
                requires_human_approval=True,
            )
        if not bool(rule.get("agent_may_merge", False)):
            return AuthorityDecision(
                allowed=False,
                state="AWAITING_HUMAN_APPROVAL",
                reason="policy forbids autonomous agent merge of protected branches",
                branch=branch,
                protected=True,
                requires_human_approval=requires_human,
            )

    if requires_human and not explicit_human_approval:
        return AuthorityDecision(
            allowed=False,
            state="AWAITING_HUMAN_APPROVAL",
            reason="explicit human approval event is required",
            branch=branch,
            protected=True,
            requires_human_approval=True,
        )

    return AuthorityDecision(
        allowed=True,
        state="ALLOW",
        reason="protected branch requirements satisfied",
        branch=branch,
        protected=True,
        requires_human_approval=requires_human,
    )


def main() -> int:
    p = argparse.ArgumentParser(description="Evaluate authority for a protected-branch mutation")
    p.add_argument("--branch", required=True)
    p.add_argument("--actor-kind", choices=["human", "agent", "automation"], required=True)
    p.add_argument("--explicit-human-approval", action="store_true")
    p.add_argument("--via-pull-request", action="store_true")
    args = p.parse_args()
    decision = authorize(
        branch=args.branch,
        actor_kind=args.actor_kind,
        explicit_human_approval=args.explicit_human_approval,
        via_pull_request=args.via_pull_request,
    )
    print(json.dumps(asdict(decision), ensure_ascii=False, indent=2))
    return 0 if decision.allowed else 3


if __name__ == "__main__":
    raise SystemExit(main())
