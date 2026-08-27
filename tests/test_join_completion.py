import json

from agentos_node.onboarding import build_join_regression_report
from agentos_node.session_bridge import FileSessionBridge, describe_bridge


def test_join_regression_requires_no_local_capability_loss():
    before = {'capabilities': ['shell.exec', 'filesystem.read']}
    after = {'capabilities': ['shell.exec', 'filesystem.read', 'agent.chat'], 'surface_inventory': {}}
    bootstrap = {
        'schema': 'agentos.node-bootstrap/v0.1',
        'inherited_realm_capabilities': ['context.harvest'],
        'canonical_capabilities': [{'capability_id': 'layoutlib.profile', 'state_id': 'capstate-1'}],
    }
    report = build_join_regression_report(
        realm_id='realm-test', node_id='node-b', before_manifest=before, after_manifest=after, bootstrap=bootstrap,
    )
    assert report['node_ready'] is True
    assert report['checks']['local_capability_non_regression'] is True
    assert report['checks']['canonical_capabilities'] == ['layoutlib.profile']
    assert report['one_uplift_observed'] is True


def test_join_regression_fails_when_capability_disappears():
    report = build_join_regression_report(
        realm_id='realm-test', node_id='node-b',
        before_manifest={'capabilities': ['shell.exec', 'filesystem.read']},
        after_manifest={'capabilities': ['filesystem.read'], 'surface_inventory': {}},
        bootstrap={'schema': 'agentos.node-bootstrap/v0.1', 'inherited_realm_capabilities': [], 'canonical_capabilities': []},
    )
    assert report['node_ready'] is False
    assert report['checks']['lost_capabilities'] == ['shell.exec']


def test_file_session_bridge_declares_and_queues_governed_operations(monkeypatch, tmp_path):
    root = tmp_path / 'antigravity'
    root.mkdir()
    (root / 'bridge.json').write_text(json.dumps({
        'schema': 'agentos.session-bridge/v0.1', 'provider': 'antigravity', 'ready': True,
        'operations': ['discover', 'snapshot', 'harvest', 'inject', 'handoff'],
    }), encoding='utf-8')
    (root / 'sessions.json').write_text(json.dumps({
        'schema': 'agentos.session-index/v0.1', 'provider': 'antigravity',
        'sessions': [{'session_id': 's1', 'title': 'AgentOS'}],
    }), encoding='utf-8')
    monkeypatch.setenv('AGENTOS_ANTIGRAVITY_BRIDGE', str(root))

    descriptor = describe_bridge('antigravity')
    assert descriptor['ready'] is True
    assert 'agent.context.harvest' in descriptor['capabilities']

    bridge = FileSessionBridge.from_environment('antigravity')
    assert bridge.discover()['sessions'][0]['session_id'] == 's1'
    request = bridge.request('handoff', session_id='s1', payload={'goal': 'continue'})
    queued = root / 'requests' / f"{request['request_id']}.json"
    assert queued.exists()
