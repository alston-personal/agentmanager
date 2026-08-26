from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class BenchmarkMetrics:
    task_success: float
    repeated_errors: int
    user_clarifications: int
    continuity_recovery: float
    realm_capability_usage: int
    inherited_cognition_usage: int
    evidence_returned: int

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> 'BenchmarkMetrics':
        return cls(
            task_success=float(raw.get('task_success', 0.0)),
            repeated_errors=int(raw.get('repeated_errors', 0)),
            user_clarifications=int(raw.get('user_clarifications', 0)),
            continuity_recovery=float(raw.get('continuity_recovery', 0.0)),
            realm_capability_usage=int(raw.get('realm_capability_usage', 0)),
            inherited_cognition_usage=int(raw.get('inherited_cognition_usage', 0)),
            evidence_returned=int(raw.get('evidence_returned', 0)),
        )


def compare_before_after(before: BenchmarkMetrics, after: BenchmarkMetrics) -> dict[str, Any]:
    """Compare one Node with ONE disabled/enabled.

    Positive deltas always mean improvement in the returned `uplift` object.
    The function intentionally reports dimensions independently instead of
    collapsing cognition, capability and interaction into one opaque score.
    """
    uplift = {
        'task_success': after.task_success - before.task_success,
        'repeated_errors': before.repeated_errors - after.repeated_errors,
        'user_clarifications': before.user_clarifications - after.user_clarifications,
        'continuity_recovery': after.continuity_recovery - before.continuity_recovery,
        'realm_capability_usage': after.realm_capability_usage - before.realm_capability_usage,
        'inherited_cognition_usage': after.inherited_cognition_usage - before.inherited_cognition_usage,
        'evidence_returned': after.evidence_returned - before.evidence_returned,
    }
    improved_dimensions = sum(1 for value in uplift.values() if value > 0)
    regressed_dimensions = sum(1 for value in uplift.values() if value < 0)
    return {
        'schema': 'agentos.one-uplift-report/v0.1',
        'before': before.__dict__,
        'after': after.__dict__,
        'uplift': uplift,
        'improved_dimensions': improved_dimensions,
        'regressed_dimensions': regressed_dimensions,
        'one_uplift_observed': improved_dimensions > 0 and regressed_dimensions == 0,
    }
