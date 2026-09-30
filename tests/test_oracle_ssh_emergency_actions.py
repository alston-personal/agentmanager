import tempfile
from pathlib import Path

from agent_core.controller_api import ControllerService
from agent_core.node_registry import NodeRegistry
from agent_core.realm_fabric import RealmFabricStore


def _fixture():
    tmp = tempfile.TemporaryDirectory()
    root = Path(tmp.name)
    registry = NodeRegistry(path=root / 'nodes.json')
    fabric = RealmFabricStore(path=root / 'fabric.json', node_registry=registry)
    fabric.initialize_realm('realm-test')
    manifest = {
        'schema': 'agentos.node-manifest/v0.1',
        'realm_id': 'realm-test',
        'node_id': 'oracle-exec',
        'role': 'client',
        'hostname': 'oracle',
        'platform': 'Linux',
        'platform_release': 'test',
        'capabilities': ['node.ssh.inspect', 'node.ssh.recover', 'node.runner.inspect', 'node.runner.recover'],
        'tool_presence': {},
        'surface_inventory': {'surfaces': []},
        'workspace_roots': {'readable': ['/home/ubuntu/AgentOS'], 'writable': ['/home/ubuntu/AgentOS']},
    }
    invite = fabric.create_invite(expires_minutes=5, label='ssh-emergency')
    enrolled = fabric.enroll(invite_id=invite['invite_id'], code=invite['code'], manifest=manifest)
    fabric.record_heartbeat({
        'schema': 'agentos.node-heartbeat/v0.1',
        'realm_id': 'realm-test',
        'node_id': 'oracle-exec',
        'status': 'online',
        'observed_at': None,
        'uptime_seconds': 1,
        'surface_count': 0,
        'manifest': manifest,
    }, enrolled['node_token'])
    return tmp, fabric


def test_controller_routes_only_typed_ssh_inspect():
    tmp, fabric = _fixture()
    try:
        out = ControllerService(fabric).dispatch('oracle-exec', {'action': 'node.ssh.inspect'})
        assert out['ok'] is True
        task = fabric.load()['tasks']['oracle-exec'][0]
        assert task['action'] == 'node.ssh.inspect'
        assert 'executable' not in task
        assert 'argv' not in task
    finally:
        tmp.cleanup()


def test_controller_routes_only_typed_ssh_recover():
    tmp, fabric = _fixture()
    try:
        out = ControllerService(fabric).dispatch('oracle-exec', {'action': 'node.ssh.recover'})
        assert out['ok'] is True
        task = fabric.load()['tasks']['oracle-exec'][0]
        assert task['action'] == 'node.ssh.recover'
        assert 'executable' not in task
        assert 'argv' not in task
    finally:
        tmp.cleanup()


def test_controller_routes_only_typed_runner_inspect():
    tmp, fabric = _fixture()
    try:
        out = ControllerService(fabric).dispatch('oracle-exec', {
            'action': 'node.runner.inspect',
            'executable': 'bash',
            'argv': ['-c', 'id'],
        })
        assert out['ok'] is True
        task = fabric.load()['tasks']['oracle-exec'][0]
        assert task['action'] == 'node.runner.inspect'
        assert 'executable' not in task
        assert 'argv' not in task
    finally:
        tmp.cleanup()


def test_controller_routes_only_typed_runner_recover():
    tmp, fabric = _fixture()
    try:
        out = ControllerService(fabric).dispatch('oracle-exec', {
            'action': 'node.runner.recover',
            'unit': 'evil.service',
            'argv': ['restart', 'evil.service'],
        })
        assert out['ok'] is True
        task = fabric.load()['tasks']['oracle-exec'][0]
        assert task['action'] == 'node.runner.recover'
        assert 'unit' not in task
        assert 'argv' not in task
    finally:
        tmp.cleanup()
