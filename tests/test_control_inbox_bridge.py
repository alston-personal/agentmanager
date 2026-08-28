from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from agent_core.control_inbox_bridge import BridgeConfig, ControlInboxBridge, _task_id
from agent_core.controller_api import ControllerService


class FakeRegistry:
    def node_map(self):
        return {
            'schema': 'agentos.node-map/v0.1',
            'realm_id': 'realm-test',
            'node_count': 1,
            'online_node_count': 1,
            'nodes': [{
                'node_id': 'node-a',
                'status': 'online',
                'capabilities': ['agent.surface.inspect', 'desktop.open_url'],
            }],
            'realm_capabilities': ['agent.surface.inspect', 'desktop.open_url'],
            'realm_tool_presence': [],
            'realm_surface_providers': [],
        }


class FakeFabric:
    def __init__(self):
        self.node_registry = FakeRegistry()
        self.data = {'tasks': {'node-a': []}, 'receipts': {}}

    def load(self):
        return self.data

    def queue_task(self, node_id, task):
        queued = {**task, 'queued_at': '2026-08-28T00:00:00Z'}
        self.data['tasks'].setdefault(node_id, []).append(queued)
        return queued

    def get_receipt(self, task_id):
        return self.data['receipts'].get(task_id)


class FakeGitHub:
    def __init__(self, comments):
        self._comments = comments
        self.results = []

    def comments(self):
        return list(self._comments)

    def post_result(self, payload):
        self.results.append(payload)


class FakeOne:
    def __init__(self, receipt=None):
        self.dispatched = []
        self._receipt = receipt

    def dispatch(self, node_id, command):
        self.dispatched.append((node_id, command))
        return {'ok': True, 'task_id': _task_id(command['command_id']), 'state': 'queued'}

    def receipt(self, task_id):
        return self._receipt


def _config(tmp_path: Path) -> BridgeConfig:
    return BridgeConfig(
        repository='alston-personal/agentmanager',
        issue_number=50,
        allowed_login='alstonhuang',
        github_token='unused',
        controller_token='unused',
        one_url='http://127.0.0.1:8780',
        state_path=tmp_path / 'state.json',
        poll_seconds=1,
        receipt_wait_seconds=1,
    )


def _command(*, expired: bool = False):
    now = datetime.now(timezone.utc).replace(microsecond=0)
    issued = now - timedelta(minutes=2) if expired else now - timedelta(seconds=1)
    expires = now - timedelta(seconds=1) if expired else now + timedelta(minutes=2)
    return {
        'schema': 'agentos.control-command/v0.1',
        'command_id': 'cmd_test_1',
        'issued_at': issued.isoformat().replace('+00:00', 'Z'),
        'expires_at': expires.isoformat().replace('+00:00', 'Z'),
        'node_id': 'node-a',
        'action': 'agent.surface.inspect',
        'args': {},
    }


def test_controller_dispatch_reuses_same_task_id_without_duplicate_queue():
    fabric = FakeFabric()
    controller = ControllerService(fabric)
    request = {'action': 'agent.surface.inspect', 'task_id': 'ctl_same'}

    first = controller.dispatch('node-a', request)
    second = controller.dispatch('node-a', request)

    assert first['reused'] is False
    assert second['reused'] is True
    assert second['state'] == 'queued'
    assert len(fabric.data['tasks']['node-a']) == 1


def test_bridge_dispatches_allowed_fresh_command_and_posts_receipt(tmp_path: Path):
    command = _command()
    github = FakeGitHub([{'id': 101, 'user': {'login': 'alstonhuang'}, 'body': __import__('json').dumps(command)}])
    receipt = {
        'schema': 'agentos.node-receipt/v0.1',
        'node_id': 'node-a',
        'task_id': _task_id(command['command_id']),
        'action': 'agent.surface.inspect',
        'ok': True,
    }
    one = FakeOne(receipt)
    bridge = ControlInboxBridge(_config(tmp_path), github=github, one=one)

    assert bridge.process_once() == 1
    assert one.dispatched[0][0] == 'node-a'
    assert github.results[0]['status'] == 'completed'
    assert github.results[0]['receipt']['ok'] is True

    # Local state prevents replay on the next poll.
    assert bridge.process_once() == 0
    assert len(one.dispatched) == 1


def test_bridge_ignores_untrusted_author(tmp_path: Path):
    command = _command()
    github = FakeGitHub([{'id': 102, 'user': {'login': 'someone-else'}, 'body': __import__('json').dumps(command)}])
    one = FakeOne()
    bridge = ControlInboxBridge(_config(tmp_path), github=github, one=one)

    assert bridge.process_once() == 0
    assert one.dispatched == []
    assert github.results == []


def test_bridge_rejects_expired_command_without_dispatch(tmp_path: Path):
    command = _command(expired=True)
    github = FakeGitHub([{'id': 103, 'user': {'login': 'alstonhuang'}, 'body': __import__('json').dumps(command)}])
    one = FakeOne()
    bridge = ControlInboxBridge(_config(tmp_path), github=github, one=one)

    assert bridge.process_once() == 1
    assert one.dispatched == []
    assert github.results[0]['status'] == 'error'
    assert 'command expired' in github.results[0]['error']
