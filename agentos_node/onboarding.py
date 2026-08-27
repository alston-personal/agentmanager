from __future__ import annotations

from typing import Any


def build_join_regression_report(
    *,
    realm_id: str,
    node_id: str,
    before_manifest: dict[str, Any],
    after_manifest: dict[str, Any],
    bootstrap: dict[str, Any],
    report_kind: str = 'join-regression',
) -> dict[str, Any]:
    if report_kind not in {'join-regression', 'readiness-regression'}:
        raise ValueError('invalid regression report kind')
    before_caps = set(before_manifest.get('capabilities') or [])
    after_caps = set(after_manifest.get('capabilities') or [])
    lost_caps = sorted(before_caps - after_caps)
    inherited_caps = sorted(set(bootstrap.get('inherited_realm_capabilities') or []))
    canonical = list(bootstrap.get('canonical_capabilities') or [])
    canonical_ids = sorted({str(item.get('capability_id')) for item in canonical if isinstance(item, dict) and item.get('capability_id')})

    before = {
        'task_success': 1.0,
        'repeated_errors': 0,
        'user_clarifications': 0,
        'continuity_recovery': 0.0,
        'realm_capability_usage': 0,
        'inherited_cognition_usage': 0,
        'evidence_returned': 0,
    }
    after = {
        'task_success': 1.0 if not lost_caps else 0.0,
        'repeated_errors': len(lost_caps),
        'user_clarifications': 0,
        'continuity_recovery': 1.0 if canonical_ids else 0.0,
        'realm_capability_usage': len(inherited_caps),
        'inherited_cognition_usage': len(canonical_ids),
        'evidence_returned': 1,
    }
    uplift = {
        'task_success': after['task_success'] - before['task_success'],
        'repeated_errors': before['repeated_errors'] - after['repeated_errors'],
        'user_clarifications': before['user_clarifications'] - after['user_clarifications'],
        'continuity_recovery': after['continuity_recovery'] - before['continuity_recovery'],
        'realm_capability_usage': after['realm_capability_usage'] - before['realm_capability_usage'],
        'inherited_cognition_usage': after['inherited_cognition_usage'] - before['inherited_cognition_usage'],
        'evidence_returned': after['evidence_returned'] - before['evidence_returned'],
    }
    improved = sum(1 for value in uplift.values() if value > 0)
    regressed = sum(1 for value in uplift.values() if value < 0)
    ready = not lost_caps and bootstrap.get('schema') == 'agentos.node-bootstrap/v0.1'
    return {
        'schema': 'agentos.one-uplift-report/v0.1',
        'report_kind': report_kind,
        'realm_id': realm_id,
        'node_id': node_id,
        'before': before,
        'after': after,
        'uplift': uplift,
        'improved_dimensions': improved,
        'regressed_dimensions': regressed,
        'one_uplift_observed': improved > 0 and regressed == 0,
        'node_ready': ready,
        'checks': {
            'local_capability_non_regression': not lost_caps,
            'lost_capabilities': lost_caps,
            'inherited_realm_capabilities': inherited_caps,
            'canonical_capabilities': canonical_ids,
            'surface_inventory_present': isinstance(after_manifest.get('surface_inventory'), dict),
        },
    }
