from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from agent_core.capability_attestation import (
    derive_visual_loop_attestation,
    effective_capability_attestation,
    validate_capability_attestation,
)
from agent_core.node_registry import NodeRegistry


def _iso(value: datetime) -> str:
    return value.replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def _manifest(node_id: str = 'visual-node') -> dict:
    return {
        'schema': 'agentos.node-manifest/v0.1',
        'realm_id': 'realm-test',
        'node_id': node_id,
        'role': 'client',
        'hostname': node_id,
        'platform': 'Windows',
        'platform_release': 'test',
        'capabilities': [
            'desktop.screenshot',
            'desktop.mouse',
            'desktop.keyboard',
        ],
        'tool_presence': {},
        'surface_inventory': {},
    }


def _heartbeat(registry: NodeRegistry, node_id: str = 'visual-node') -> None:
    registry.record_heartbeat({
        'schema': 'agentos.node-heartbeat/v0.1',
        'realm_id': 'realm-test',
        'node_id': node_id,
        'role': 'client',
        'status': 'online',
        'uptime_seconds': 1,
    })


def _attestation(capability_id: str, *, runtime_session_id: str = 'desktop-session-1') -> dict:
    now = datetime.now(timezone.utc)
    return {
        'schema': 'agentos.capability-attestation/v0.1',
        'node_id': 'visual-node',
        'capability_id': capability_id,
        'verification_state': 'verified',
        'probe_class': 'desktop-smoke/v1',
        'provider_id': 'windows-interactive-desktop',
        'executor_id': 'desktop-executor-1',
        'runtime_session_id': runtime_session_id,
        'observed_at': _iso(now),
        'valid_until': _iso(now + timedelta(minutes=5)),
        'receipt_id': f'receipt-{capability_id}',
    }


def test_advertised_capability_is_not_verified_without_attestation(tmp_path: Path) -> None:
    registry = NodeRegistry(tmp_path / 'nodes.json')
    registry.register_manifest(_manifest())
    _heartbeat(registry)

    node_map = registry.node_map()
    node = node_map['nodes'][0]
    assert 'desktop.screenshot' in node['advertised_capabilities']
    assert 'desktop.screenshot' in node_map['realm_advertised_capabilities']
    assert 'desktop.screenshot' not in node['verified_capabilities']
    assert 'desktop.screenshot' not in node_map['realm_verified_capabilities']
    assert not registry.has_verified_capability('visual-node', 'desktop.screenshot')


def test_fresh_same_session_primitives_verify_visual_loop(tmp_path: Path) -> None:
    registry = NodeRegistry(tmp_path / 'nodes.json')
    registry.register_manifest(_manifest())
    _heartbeat(registry)

    for capability_id in ('desktop.screenshot', 'desktop.mouse', 'desktop.keyboard'):
        registry.record_capability_attestation(_attestation(capability_id))

    node_map = registry.node_map()
    node = node_map['nodes'][0]
    assert set(node['verified_capabilities']) == {
        'desktop.screenshot',
        'desktop.mouse',
        'desktop.keyboard',
        'desktop.visual-loop',
    }
    assert 'desktop.visual-loop' in node_map['realm_verified_capabilities']
    assert registry.has_verified_capability('visual-node', 'desktop.visual-loop')
    derived = node['derived_capability_attestations'][0]
    assert derived['verification_state'] == 'verified'
    assert derived['runtime_session_id'] == 'desktop-session-1'


def test_visual_loop_fails_closed_when_runtime_boundary_differs() -> None:
    items = [
        _attestation('desktop.screenshot'),
        _attestation('desktop.mouse'),
        _attestation('desktop.keyboard', runtime_session_id='desktop-session-2'),
    ]
    derived = derive_visual_loop_attestation(items)
    assert derived['verification_state'] == 'unknown'
    assert derived['verification_reason'] == 'runtime_boundary_mismatch'


def test_expired_attestation_does_not_remain_verified() -> None:
    item = _attestation('desktop.screenshot')
    item['observed_at'] = '2020-01-01T00:00:00Z'
    item['valid_until'] = '2020-01-01T00:05:00Z'
    effective = effective_capability_attestation(item)
    assert effective['reported_verification_state'] == 'verified'
    assert effective['verification_state'] == 'unknown'
    assert effective['attestation_stale'] is True
    assert effective['verification_reason'] == 'attestation_expired'


def test_node_not_online_invalidates_live_verified_projection(tmp_path: Path) -> None:
    registry = NodeRegistry(tmp_path / 'nodes.json')
    registry.register_manifest(_manifest())
    registry.record_capability_attestation(_attestation('desktop.screenshot'))

    node = registry.node_map()['nodes'][0]
    assert node['reported_status'] == 'unknown'
    assert 'desktop.screenshot' not in node['verified_capabilities']
    effective = node['capability_attestations'][0]
    assert effective['verification_state'] == 'unknown'
    assert effective['verification_reason'] == 'node_not_online'


def test_manifest_refresh_preserves_live_attestations(tmp_path: Path) -> None:
    registry = NodeRegistry(tmp_path / 'nodes.json')
    registry.register_manifest(_manifest())
    _heartbeat(registry)
    registry.record_capability_attestation(_attestation('desktop.screenshot'))

    refreshed = _manifest()
    refreshed['platform_release'] = 'next'
    registry.register_manifest(refreshed)

    node = registry.node_map()['nodes'][0]
    assert node['platform_release'] == 'next'
    assert 'desktop.screenshot' in node['verified_capabilities']


def test_attestation_cannot_smuggle_authority_or_raw_image_payload() -> None:
    with pytest.raises(ValueError, match='authorization'):
        validate_capability_attestation({
            **_attestation('desktop.screenshot'),
            'authorized': True,
        })

    with pytest.raises(ValueError, match='image_base64'):
        validate_capability_attestation({
            **_attestation('desktop.screenshot'),
            'evidence': {'image_base64': 'AAAA'},
        })


def test_attestation_for_unknown_node_is_rejected(tmp_path: Path) -> None:
    registry = NodeRegistry(tmp_path / 'nodes.json')
    with pytest.raises(KeyError):
        registry.record_capability_attestation(_attestation('desktop.screenshot'))
