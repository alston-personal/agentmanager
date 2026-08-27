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
    inventory = discover_surfaces(
        process_names={'antigravity'},
        which=_which_factory({'antigravity': '/opt/antigravity'}),
    )

    surface = next(x for x in inventory['surfaces'] if x['provider'] == 'antigravity')
    assert surface['kind'] == 'ide-agent'
    assert surface['running'] is True
    assert surface['attachable'] is False
    assert 'agent.session.inspect' in surface['capabilities']
    assert 'agent.session.attach' not in surface['capabilities']


def test_antigravity_bridge_promotes_session_bridge_capabilities(monkeypatch):
    monkeypatch.setenv('AGENTOS_ANTIGRAVITY_BRIDGE', 'local-relay')
    inventory = discover_surfaces(
        process_names={'antigravity'},
        which=_which_factory({'antigravity': '/opt/antigravity'}),
    )

    surface = next(x for x in inventory['surfaces'] if x['provider'] == 'antigravity')
    assert surface['attachable'] is True
    assert 'agent.session.attach' in surface['capabilities']
    assert 'agent.context.inject' in surface['capabilities']
    assert 'agent.session.handoff' in surface['capabilities']


def test_node_manifest_advertises_surface_inventory(monkeypatch, tmp_path):
    monkeypatch.setattr('agentos_node.thin_client.discover_surfaces', lambda: {
        'schema': 'agentos.surface-inventory/v0.1',
        'surfaces': [{
            'surface_id': 'ide-agent:antigravity',
            'kind': 'ide-agent',
            'provider': 'antigravity',
            'executable': 'C:/Agent/antigravity.exe',
            'running': True,
            'capabilities': ['agent.chat', 'agent.session.inspect'],
            'attachable': False,
            'metadata': {},
        }],
        'surface_count': 1,
        'capabilities': ['agent.chat', 'agent.session.inspect'],
        'providers': ['antigravity'],
    })
    policy = ThinClientPolicy(readable_roots=(tmp_path,), writable_roots=(tmp_path,))
    client = ThinClient(NodeIdentity('realm-test', 'host-01'), policy)

    manifest = client.capability_manifest()
    assert manifest['node_id'] == 'host-01'
    assert manifest['surface_inventory']['providers'] == ['antigravity']
    assert 'agent.chat' in manifest['capabilities']
    assert 'agent.surface.inspect' in manifest['capabilities']


def test_node_registry_preserves_surface_inventory(tmp_path):
    registry = NodeRegistry(tmp_path / 'nodes.json')
    manifest = {
        'schema': 'agentos.node-manifest/v0.1',
        'realm_id': 'realm-test',
        'node_id': 'host-01',
        'role': 'client',
        'hostname': 'HOST-01',
        'platform': 'Windows',
        'platform_release': '11',
        'capabilities': ['agent.chat'],
        'tool_presence': {'antigravity': 'C:/Agent/antigravity.exe'},
        'surface_inventory': {
            'schema': 'agentos.surface-inventory/v0.1',
            'surface_count': 1,
            'providers': ['antigravity'],
            'capabilities': ['agent.chat'],
            'surfaces': [{'provider': 'antigravity', 'kind': 'ide-agent'}],
        },
    }
    entry = registry.register_manifest(manifest)
    assert entry['node_id'] == 'host-01'
    assert entry['surface_inventory']['surface_count'] == 1

    node_map = registry.node_map()
    assert node_map['node_count'] == 1
    assert node_map['realm_surface_providers'] == ['antigravity']
