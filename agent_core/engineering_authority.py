from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_STATE_PATH = Path('.agentos/engineering/state.json')


@dataclass(frozen=True)
class EngineeringDecision:
    role: str
    branch: str
    active_branch: str
    allowed: bool
    permission: str
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {
            'schema': 'agentos.engineering-decision/v0.1',
            'role': self.role,
            'branch': self.branch,
            'active_branch': self.active_branch,
            'allowed': self.allowed,
            'permission': self.permission,
            'reason': self.reason,
        }


def load_engineering_state(path: str | Path = DEFAULT_STATE_PATH) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    if data.get('schema') != 'agentos.engineering-state/v0.1':
        raise ValueError('invalid engineering state schema')
    authority = data.get('authority')
    if not isinstance(authority, dict) or not authority.get('active_branch'):
        raise ValueError('engineering state missing active branch')
    return data


def evaluate_branch_write(*, role: str, branch: str, state: dict[str, Any]) -> EngineeringDecision:
    role = str(role or 'unknown')
    branch = str(branch or '')
    authority = state['authority']
    active_branch = str(authority['active_branch'])
    merge_target = str(authority.get('merge_target') or 'main')
    owner_role = str(authority.get('owner_role') or 'agentos-engineering')

    if branch == merge_target:
        return EngineeringDecision(
            role=role,
            branch=branch,
            active_branch=active_branch,
            allowed=False,
            permission='proposal-only',
            reason=f'{merge_target} is integration-only; use a pull request from {active_branch}',
        )

    if role == owner_role and branch == active_branch:
        return EngineeringDecision(
            role=role,
            branch=branch,
            active_branch=active_branch,
            allowed=True,
            permission='write',
            reason='single engineering owner is writing the canonical active branch',
        )

    if role == 'experiment-agent' and branch.startswith('experiment/'):
        return EngineeringDecision(
            role=role,
            branch=branch,
            active_branch=active_branch,
            allowed=True,
            permission='isolated-experiment-write',
            reason='experiment agents may write only isolated experiment branches',
        )

    return EngineeringDecision(
        role=role,
        branch=branch,
        active_branch=active_branch,
        allowed=False,
        permission='proposal-only',
        reason='another engineering authority owns the active integration goal',
    )


def require_branch_write(*, role: str, branch: str, state: dict[str, Any]) -> EngineeringDecision:
    decision = evaluate_branch_write(role=role, branch=branch, state=state)
    if not decision.allowed:
        raise PermissionError(decision.reason)
    return decision
