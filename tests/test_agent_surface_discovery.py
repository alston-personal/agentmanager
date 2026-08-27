import json
from pathlib import Path

from agent_core.node_registry import NodeRegistry
from agentos_node.agent_surfaces import discover_surfaces
from agentos_node.thin_client import NodeIdentity, ThinClient, ThinClientPolicy


def _which_factory(values):
    def which(name):
        return values.get(name)
    return which


def test_antigravity_is_surface_inside_node_not_node_identity(monkeypatch):
    monkeypatch.delenv('AGENTOS_ANTIGRAVITY_BRIDGE', raising=False)
    inventory = discover_surfaces(process_names={'antigravity'}, which=_which_factory({'antigravity': '/opt/antigravity'}))
    surface = next(x for x in inventory['surfaces'] if x['provider'] == 'antigravity')
    assert surface['kind'] == 'ide-agent'
    assert surface['running'] is True
    assert surface['attachable'] is False
    assert 'agent.session.attach' not in surface['capabilities']


def test_antigravity_bridge_promotes_only_declared_capabilities(monkeypatch, tmp_path):
    bridge = tmp_path / 'bridge'
    bridge.mkdir()
    (bridge / 'bridge.json').write_text(json.dumps({
        'schema': 'agentos.session-bridge/v0.1',
        'provider': 'antigravity',
        'ready': True,
        'operations': ['discover', 'snapshot', 'inject', 'handoff'],
    }), encoding='utf-8')
    monkeypatch.setenv('AGENTOS_ANTIGRAVITY_BRIDGE', str(bridge))
    inventory = discover_surfaces(process_names={'antigravity'}, which=_which_factory({'antigravity': '/opt/antigravity'}))
    surface = next(x for x in inventory['surfaces'] if x['provider'] == 'antigravity')
    assert surface['attachable'] is False
    assert 'agent.session.discover' in surface['capabilities']
    assert 'agent.session.inspect' in surface['capabilities']
    assert 'agent.context.inject' in surface['capabilities']
    assert 'agent.session.handoff' in surface['capabilities']
    assert 'agent.context.harvest' not in surface['capabilities']


def test_node_manifest_advertises_surface_inventory(monkeypatch, tmp_path):
    monkeypatch.setattr('agentos_node.thin_client.discover_surfaces', lambda: {
        'schema': 'agentos.surface-inventory/v0.1',
        'surfaces': [{'surface_id': 'ide-agent:antigravity', 'kind': 'ide-agent', 'provider': 'antigravity', 'executable': 'C:/Agent/antigravity.exe', 'running': True, 'capabilities': ['agent.chat'], 'attachable': False, 'metadata': {}}],
        'surface_count': 1, 'capabilities': ['agent.chat'], 'providers': ['antigravity'],
    })
    policy = ThinClientPolicy(readable_roots=(tmp_path,), writable_roots=(tmp_path,))
    client = ThinClient(NodeIdentity('realm-test', 'host-01'), policy)
    manifest = client.capability_manifest()
    assert manifest['node_id'] == 'host-01'
    assert manifest['surface_inventory']['providers'] == ['antigravity']
    assert 'agent.chat' in manifest['capabilities']
    assert 'agent.surface.inspect' in manifest['capabilities']
    heartbeat = client.heartbeat()
    assert heartbeat['manifest']['node_id'] == 'host-01'
    assert heartbeat['surface_count'] == 1


def test_node_registry_preserves_surface_inventory(tmp_path):
    registry = NodeRegistry(tmp_path / 'nodes.json')
    manifest = {
        'schema': 'agentos.node-manifest/v0.1', 'realm_id': 'realm-test', 'node_id': 'host-01', 'role': 'client',
        'hostname': 'HOST-01', 'platform': 'Windows', 'platform_release': '11', 'capabilities': ['agent.chat'],
        'tool_presence': {'antigravity': 'C:/Agent/antigravity.exe'},
        'surface_inventory': {'schema': 'agentos.surface-inventory/v0.1', 'surface_count': 1, 'providers': ['antigravity'], 'capabilities': ['agent.chat'], 'surfaces': [{'provider': 'antigravity', 'kind': 'ide-agent'}]},
    }
    entry = registry.register_manifest(manifest)
    assert entry['surface_inventory']['surface_count'] == 1
    node_map = registry.node_map()
    assert node_map['node_count'] == 1
    assert node_map['realm_surface_providers'] == ['antigravity']


def test_heartbeat_refreshes_surface_inventory(tmp_path):
    registry = NodeRegistry(tmp_path / 'nodes.json')
    initial = {
        'schema': 'agentos.node-manifest/v0.1', 'realm_id': 'realm-test', 'node_id': 'host-01', 'role': 'client',
        'hostname': 'HOST-01', 'platform': 'Windows', 'platform_release': '11', 'capabilities': ['tool.presence'], 'tool_presence': {},
        'surface_inventory': {'schema': 'agentos.surface-inventory/v0.1', 'surface_count': 0, 'providers': [], 'capabilities': [], 'surfaces': []},
    }
    registry.register_manifest(initial)
    refreshed = dict(initial)
    refreshed['capabilities'] = ['agent.chat', 'tool.presence']
    refreshed['surface_inventory'] = {'schema': 'agentos.surface-inventory/v0.1', 'surface_count': 1, 'providers': ['antigravity'], 'capabilities': ['agent.chat'], 'surfaces': [{'provider': 'antigravity', 'kind': 'ide-agent'}]}
    registry.record_heartbeat({'schema': 'agentos.node-heartbeat/v0.1', 'realm_id': 'realm-test', 'node_id': 'host-01', 'status': 'online', 'surface_count': 1, 'manifest': refreshed})
    node = registry.node_map()['nodes'][0]
    assert node['surface_inventory']['providers'] == ['antigravity']
    assert 'agent.chat' in node['capabilities']
