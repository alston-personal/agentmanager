from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def _canonical_states(root: Path) -> list[dict[str, Any]]:
    states: list[dict[str, Any]] = []
    state_root = root / 'states'
    if not state_root.exists():
        return states
    for path in sorted(state_root.glob('*/canonical.json')):
        try:
            payload = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError):
            continue
        if payload.get('schema') != 'agentos.capability-state/v1':
            continue
        states.append({
            'capability_id': payload.get('capability_id'),
            'state_id': payload.get('state_id'),
            'version': payload.get('version'),
            'confidence': payload.get('confidence'),
            'support': payload.get('support'),
        })
    return states


def bootstrap_snapshot(fabric: Any, node_id: str, token: str) -> dict[str, Any]:
    """Return inherited Realm capability/cognition available to one enrolled Node."""
    fabric.authenticate(node_id, token)
    node_map = fabric.node_registry.node_map()
    nodes = list(node_map.get('nodes') or [])
    own = next((node for node in nodes if node.get('node_id') == node_id), None)
    if own is None:
        raise KeyError(node_id)

    inherited_caps = sorted({
        cap
        for node in nodes
        if node.get('node_id') != node_id and node.get('status') != 'offline'
        for cap in (node.get('capabilities') or [])
    })
    inherited_surfaces = sorted({
        str(surface.get('provider'))
        for node in nodes
        if node.get('node_id') != node_id and node.get('status') != 'offline'
        for surface in ((node.get('surface_inventory') or {}).get('surfaces') or [])
        if isinstance(surface, dict) and surface.get('provider')
    })

    data_root = Path(os.environ.get('AGENT_DATA_ROOT', '/home/ubuntu/agent-data'))
    canonical = _canonical_states(data_root / 'runtime' / 'capabilities')
    return {
        'schema': 'agentos.node-bootstrap/v0.1',
        'realm_id': node_map.get('realm_id'),
        'node_id': node_id,
        'node': own,
        'realm_node_count': node_map.get('node_count', 0),
        'realm_capabilities': list(node_map.get('realm_capabilities') or []),
        'inherited_realm_capabilities': inherited_caps,
        'inherited_surface_providers': inherited_surfaces,
        'canonical_capabilities': canonical,
        'canonical_capability_count': len(canonical),
    }


def record_join_regression(fabric: Any, node_id: str, token: str, report: dict[str, Any]) -> dict[str, Any]:
    fabric.authenticate(node_id, token)
    if report.get('schema') != 'agentos.one-uplift-report/v0.1':
        raise ValueError('invalid ONE uplift report')
    if str(report.get('node_id') or '') != node_id:
        raise ValueError('uplift report node_id mismatch')
    realm_id = str(fabric.load().get('realm_id') or '')
    if str(report.get('realm_id') or '') != realm_id:
        raise ValueError('uplift report realm_id mismatch')
    return fabric.node_registry.record_benchmark(node_id, report)
