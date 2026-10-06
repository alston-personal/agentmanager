from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import pytest

from agent_core.control_inbox_bridge import (
    CONTINUATION_INSPECT_ACTION,
    BridgeConfig,
    ControlInboxBridge,
    OneControllerClient,
    OneControllerError,
    _project_receipt,
    _task_id,
)
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
                'capabilities': ['agent.surface.inspect', 'desktop.session.inspect'],
            }],
            'realm_capabilities': ['agent.surface.inspect', 'desktop.session.inspect'],
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
    def __init__(self, receipt=None, error: Exception | None = None):
        self.dispatched = []
        self._receipt = receipt
        self.error = error

    def dispatch(self, node_id, command):
        self.dispatched.append((node_id, command))
        if self.error:
            raise self.error
        return {'ok': True, 'task_id': _task_id(command['command_id']), 'state': 'queued'}

    def receipt(self, task_id):
        return self._receipt


class StubOneControllerClient(OneControllerClient):
    def __init__(self, status, payload):
        super().__init__('http://127.0.0.1:8780', 'unused')
        self.status = status
        self.payload = payload

    def _request(self, method, path, payload=None):
        return self.status, self.payload


def _config(tmp_path: Path, *, actions=None) -> BridgeConfig:
    return BridgeConfig(
        repository='alston-personal/agentmanager',
        issue_number=50,
        allowed_login='alstonhuang',
        allowed_actions=frozenset(actions or {'agent.surface.inspect', 'desktop.session.inspect'}),
        github_token='unused',
        controller_token='unused',
        one_url='http://127.0.0.1:8780',
        state_path=tmp_path / 'state.json',
        poll_seconds=1,
        receipt_wait_seconds=1,
    )


def _command(*, command_id='cmd_test_1', action='agent.surface.inspect', expired=False, schema='agentos.control-command/v0.1'):
    now = datetime.now(timezone.utc).replace(microsecond=0)
    issued = now - timedelta(minutes=2) if expired else now - timedelta(seconds=1)
    expires = now - timedelta(seconds=1) if expired else now + timedelta(minutes=2)
    return {
        'schema': schema,
        'command_id': command_id,
        'issued_at': issued.isoformat().replace('+00:00', 'Z'),
        'expires_at': expires.isoformat().replace('+00:00', 'Z'),
        'node_id': 'node-a',
        'action': action,
        'args': {},
    }


def _comment(comment_id, command, login='alstonhuang'):
    return {'id': comment_id, 'user': {'login': login}, 'body': json.dumps(command)}


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


def test_bridge_dispatches_fresh_command_and_posts_bounded_receipt(tmp_path: Path):
    command = _command()
    github = FakeGitHub([_comment(101, command)])
    receipt = {
        'schema': 'agentos.node-receipt/v0.1',
        'node_id': 'node-a',
        'task_id': _task_id(command['command_id']),
        'action': 'agent.surface.inspect',
        'ok': True,
        'surface_inventory': {
            'schema': 'agentos.surface-inventory/v0.1',
            'surface_count': 1,
            'providers': ['vscode'],
            'capabilities': ['ide.inspect'],
            'surfaces': [{
                'surface_id': 'ide:vscode', 'provider': 'vscode', 'kind': 'ide',
                'running': True, 'capabilities': ['ide.inspect'],
                'executable': 'C:/Users/private/path/code.cmd',
                'metadata': {'secret': 'do-not-publish'},
            }],
        },
    }
    one = FakeOne(receipt)
    bridge = ControlInboxBridge(_config(tmp_path), github=github, one=one)
    assert bridge.process_once() == 1
    assert len(one.dispatched) == 1
    assert github.results[0]['status'] == 'completed'
    rendered = json.dumps(github.results[0])
    assert 'C:/Users/private' not in rendered
    assert 'do-not-publish' not in rendered
    assert github.results[0]['receipt']['surface_inventory']['providers'] == ['vscode']


def test_bridge_ignores_untrusted_author(tmp_path: Path):
    command = _command()
    github = FakeGitHub([_comment(102, command, login='someone-else')])
    one = FakeOne()
    bridge = ControlInboxBridge(_config(tmp_path), github=github, one=one)
    assert bridge.process_once() == 0
    assert one.dispatched == []
    assert github.results == []


def test_invalid_schema_is_not_a_command(tmp_path: Path):
    github = FakeGitHub([_comment(103, _command(schema='something-else'))])
    one = FakeOne()
    bridge = ControlInboxBridge(_config(tmp_path), github=github, one=one)
    assert bridge.process_once() == 0
    assert one.dispatched == []
    assert github.results == []


def test_expired_command_is_rejected_before_dispatch(tmp_path: Path):
    github = FakeGitHub([_comment(104, _command(expired=True))])
    one = FakeOne()
    bridge = ControlInboxBridge(_config(tmp_path), github=github, one=one)
    assert bridge.process_once() == 1
    assert one.dispatched == []
    assert github.results[0]['status'] == 'rejected'
    assert github.results[0]['error'] == 'command_expired'


def test_duplicate_command_id_dispatches_once_even_with_two_comments(tmp_path: Path):
    first = _command(command_id='same')
    second = _command(command_id='same')
    github = FakeGitHub([_comment(105, first), _comment(106, second)])
    receipt = {'schema': 'agentos.node-receipt/v0.1', 'node_id': 'node-a', 'action': 'agent.surface.inspect', 'ok': True}
    one = FakeOne(receipt)
    bridge = ControlInboxBridge(_config(tmp_path), github=github, one=one)
    assert bridge.process_once() == 1
    assert len(one.dispatched) == 1
    assert len(github.results) == 1


def test_queued_command_is_followed_to_late_receipt_without_redispatch(tmp_path: Path):
    command = _command(command_id='late-receipt')
    github = FakeGitHub([_comment(109, command)])
    one = FakeOne(receipt=None)
    bridge = ControlInboxBridge(_config(tmp_path), github=github, one=one)

    assert bridge.process_once() == 1
    assert len(one.dispatched) == 1
    assert github.results[-1]['status'] == 'queued'

    one._receipt = {
        'schema': 'agentos.node-receipt/v0.1',
        'node_id': 'node-a',
        'task_id': _task_id(command['command_id']),
        'action': 'agent.surface.inspect',
        'ok': True,
        'surface_inventory': {
            'schema': 'agentos.surface-inventory/v0.1',
            'surface_count': 0,
            'providers': [],
            'capabilities': [],
            'surfaces': [],
        },
    }

    assert bridge.process_once() == 0
    assert len(one.dispatched) == 1
    assert github.results[-1]['status'] == 'completed'
    assert github.results[-1]['task_id'] == _task_id(command['command_id'])


def test_restart_after_claim_reports_unknown_and_never_redispatches(tmp_path: Path):
    command = _command(command_id='interrupted')
    github = FakeGitHub([])
    one = FakeOne()
    bridge = ControlInboxBridge(_config(tmp_path), github=github, one=one)
    state = bridge._load_state()
    state['commands']['interrupted'] = {
        'phase': 'claimed', 'command': command, 'claimed_at': command['issued_at'],
    }
    bridge._save_state(state)

    restarted = ControlInboxBridge(_config(tmp_path), github=github, one=one)
    assert restarted.process_once() == 0
    assert one.dispatched == []
    assert github.results[0]['status'] == 'unknown'
    assert github.results[0]['error'] == 'bridge_interrupted_after_claim'


def test_http_200_ok_dispatch_is_accepted_not_misclassified():
    client = StubOneControllerClient(200, {
        'ok': True, 'task_id': 'ctl_200', 'state': 'queued',
        'schema': 'agentos.controller-dispatch-receipt/v0.1',
    })
    result = client.dispatch('node-a', _command())
    assert result['ok'] is True
    assert result['state'] == 'queued'


@pytest.mark.parametrize('status', [400, 404, 500, 503])
def test_http_error_classification_does_not_echo_backend_body(status):
    secret_body = {'ok': False, 'error': 'authorization=Bearer SUPERSECRET internal path /srv/private'}
    client = StubOneControllerClient(status, secret_body)
    with pytest.raises(OneControllerError) as exc:
        client.dispatch('node-a', _command())
    text = str(exc.value)
    assert text == f'one_dispatch_http_{status}'
    assert 'SUPERSECRET' not in text
    assert '/srv/private' not in text


def test_malformed_2xx_dispatch_is_protocol_error():
    client = StubOneControllerClient(200, {'ok': False, 'debug': 'secret'})
    with pytest.raises(OneControllerError, match='one_dispatch_protocol_error'):
        client.dispatch('node-a', _command())


def test_unexpected_exception_text_is_not_published(tmp_path: Path):
    github = FakeGitHub([_comment(107, _command())])
    one = FakeOne(error=RuntimeError('Bearer SUPERSECRET /home/private/file'))
    bridge = ControlInboxBridge(_config(tmp_path), github=github, one=one)
    assert bridge.process_once() == 1
    assert github.results[0]['error'] == 'bridge_internal_error'
    assert 'SUPERSECRET' not in json.dumps(github.results[0])


def test_receipt_projection_drops_username_paths_and_window_titles():
    session = _project_receipt({
        'schema': 'agentos.node-receipt/v0.1', 'ok': True,
        'desktop': {'interactive': True, 'active_console_session_id': 1, 'username': 'private-user', 'pid': 99},
    }, 'desktop.session.inspect')
    assert session['desktop'] == {'interactive': True, 'active_console_session_id': 1}
    assert 'private-user' not in json.dumps(session)

    windows = _project_receipt({
        'schema': 'agentos.node-receipt/v0.1', 'ok': True, 'window_count': 2,
        'windows': [
            {'process_name': 'chrome.exe', 'title': 'private mail subject'},
            {'process_name': 'code.exe', 'title': 'C:/Users/private/project'},
        ],
    }, 'desktop.windows.inspect')
    assert windows['window_count'] == 2
    assert windows['processes'] == ['chrome.exe', 'code.exe']
    rendered = json.dumps(windows)
    assert 'private mail subject' not in rendered
    assert 'C:/Users/private' not in rendered


def test_desktop_preview_projection_keeps_only_bounded_image_evidence():
    encoded = "QUJDRA=="
    projected = _project_receipt({
        'schema': 'agentos.node-receipt/v0.1',
        'node_id': 'node-a',
        'task_id': 'preview-1',
        'action': 'desktop.preview.capture',
        'ok': True,
        'mime_type': 'image/jpeg',
        'bytes': 4,
        'sha256': 'a' * 64,
        'width': 320,
        'height': 180,
        'image_base64': encoded,
        'path': 'C:/Users/private/desktop.bmp',
        'session': {'username': 'private-user'},
    }, 'desktop.preview.capture')
    assert projected['mime_type'] == 'image/jpeg'
    assert projected['bytes'] == 4
    assert projected['width'] == 320
    assert projected['height'] == 180
    assert projected['image_base64'] == encoded
    rendered = json.dumps(projected)
    assert 'C:/Users/private' not in rendered
    assert 'private-user' not in rendered


def test_typed_desktop_receipt_projection_is_bounded_and_private():
    staged = _project_receipt({
        'schema': 'agentos.node-receipt/v0.1',
        'node_id': 'node-a',
        'task_id': 'task-stage',
        'action': 'desktop.windows.tile',
        'ok': True,
        'screen': [1920, 1080],
        'reserve_top_px': 8,
        'windows': [{
            'title_contains': 'Google Gemini',
            'zone': 'full',
            'matched': True,
            'title': 'Private Gemini conversation title',
            'hwnd': 123456,
            'moved': True,
            'rect': [4, 12, 1912, 1064],
        }],
    }, 'desktop.window.stage')
    assert staged['screen'] == [1920, 1080]
    assert staged['windows'] == [{
        'zone': 'full', 'matched': True, 'moved': True,
        'rect': [4, 12, 1912, 1064],
    }]
    rendered = json.dumps(staged)
    assert 'Private Gemini conversation title' not in rendered
    assert 'Google Gemini' not in rendered
    assert '123456' not in rendered

    clicked = _project_receipt({
        'schema': 'agentos.node-receipt/v0.1', 'ok': True,
        'operation': 'click', 'button': 'left', 'x': 900, 'y': 700,
        'session': {'username': 'private-user'},
    }, 'desktop.pointer.click')
    assert clicked['operation'] == 'click'
    assert clicked['button'] == 'left'
    assert clicked['x'] == 900 and clicked['y'] == 700
    assert 'private-user' not in json.dumps(clicked)

    typed = _project_receipt({
        'schema': 'agentos.node-receipt/v0.1', 'ok': True,
        'operation': 'type', 'characters': 42, 'text': 'private prompt',
    }, 'desktop.text.insert')
    assert typed['operation'] == 'type'
    assert typed['characters'] == 42
    assert 'private prompt' not in json.dumps(typed)


def test_typed_desktop_actions_can_be_explicitly_allowlisted(tmp_path: Path):
    config = _config(tmp_path, actions={
        'desktop.window.stage', 'desktop.pointer.click', 'desktop.text.insert',
    })
    assert config.allowed_actions == frozenset({
        'desktop.window.stage', 'desktop.pointer.click', 'desktop.text.insert',
    })


def test_executor_job_receipt_projection_preserves_governance_evidence_only():
    projected = _project_receipt({
        'schema': 'agentos.executor-job-receipt/v1',
        'job_id': 'action-12345678',
        'job_type': 'experience.regression',
        'project_id': 'agentos-core',
        'executor_class': 'openai-codex-local',
        'capability': 'agentos.experience.regression',
        'executor_available': True,
        'routable': True,
        'authorized': True,
        'successful': True,
        'credential_exposed': False,
        'classification': 'EXPERIENCE_REGRESSION_PASS',
        'experiment_id': 'exp-1',
        'verdict': 'PASS',
        'baseline_score': 0.25,
        'hydrated_score': 0.95,
        'uplift': 0.70,
        'hydration_receipt_ok': True,
        'observed_head': 'a' * 40,
        'layoutlib_release': 'v0.7.9',
        'layoutlib_manifest_files': 7,
        'layoutlib_matching_files': 7,
        'layoutlib_public_http': 200,
        'layoutlib_parity': 'EXACT',
        'stdout': 'private model output',
        'stderr': '/home/ubuntu/private/log',
        'prompt': 'private prompt',
        'session_id': 'private-session',
        'provider': 'private-provider',
        'credentials': 'do-not-publish',
    }, 'agentos.executor.job')
    assert projected['job_id'] == 'action-12345678'
    assert projected['executor_available'] is True
    assert projected['routable'] is True
    assert projected['authorized'] is True
    assert projected['successful'] is True
    assert projected['credential_exposed'] is False
    assert projected['verdict'] == 'PASS'
    assert projected['hydration_receipt_ok'] is True
    assert projected['observed_head'] == 'a' * 40
    assert projected['layoutlib_release'] == 'v0.7.9'
    assert projected['layoutlib_manifest_files'] == 7
    assert projected['layoutlib_matching_files'] == 7
    assert projected['layoutlib_public_http'] == 200
    assert projected['layoutlib_parity'] == 'EXACT'
    rendered = json.dumps(projected)
    for forbidden in ('private model output', '/home/ubuntu/private', 'private prompt', 'private-session', 'private-provider', 'do-not-publish'):
        assert forbidden not in rendered


def test_completion_executor_receipt_projects_only_bounded_owner_evidence():
    projected = _project_receipt({
        'schema': 'agentos.executor-job-receipt/v1',
        'job_id': 'action-completion-1234',
        'job_type': 'completion.market-master-1200.register',
        'project_id': 'market-master-evolution',
        'executor_class': 'completion-controller',
        'capability': 'agentos.completion.work.register',
        'executor_available': True,
        'routable': True,
        'authorized': True,
        'successful': True,
        'credential_exposed': False,
        'classification': 'COMPLETION_WORK_REGISTERED',
        'verdict': 'PASS',
        'work_id': 'market-master-1200-mvp',
        'completion_status': 'accepted',
        'completion_owner': 'role://completion.controller',
        'completion_owner_generation': 1,
        'stdout': 'private',
        'path': '/home/ubuntu/private',
    }, 'agentos.executor.job')
    assert projected['work_id'] == 'market-master-1200-mvp'
    assert projected['completion_status'] == 'accepted'
    assert projected['completion_owner'] == 'role://completion.controller'
    assert projected['completion_owner_generation'] == 1
    rendered = json.dumps(projected)
    assert 'private' not in rendered
    assert '/home/ubuntu' not in rendered


def test_runtime_converge_receipt_projects_failure_stage():
    projected = _project_receipt({
        'schema': 'agentos.runtime-converge-receipt/v1',
        'node_id': 'oracle-core-node',
        'task_id': 'action-stage-1234',
        'action': 'node.runtime.converge',
        'ok': False,
        'repository': 'alston-personal/agentmanager',
        'source_ref': 'core/integration',
        'source_commit': 'a' * 40,
        'health': 'failed',
        'rollback': 'completed',
        'classification': 'TARGET_HEALTH_FAILED_ROLLED_BACK',
        'failure_stage': 'product_employee_activation',
        'credential_exposed': False,
        'stderr': 'private',
    }, 'node.runtime.converge')
    assert projected['failure_stage'] == 'product_employee_activation'
    assert 'private' not in json.dumps(projected)


def test_runtime_converge_inspect_is_read_only_and_posts_dispatch_as_receipt(tmp_path: Path):
    command = _command(command_id='reconnect', action='node.runtime.converge.inspect')
    command['node_id'] = 'oracle-core-node'
    command['args'] = {
        'request_id': 'original-runtime-request',
        'repository': 'alston-personal/agentmanager',
        'source_ref': 'core/integration',
        'source_commit': 'a' * 40,
    }

    class ReconnectOne(FakeOne):
        def dispatch(self, node_id, command):
            self.dispatched.append((node_id, command))
            return {
                'schema': 'agentos.runtime-converge-reconnect/v1',
                'ok': True,
                'action': 'node.runtime.converge',
                'request_id': 'original-runtime-request',
                'task_id': 'action-existing-123',
                'status': 'completed',
                'classification': 'CURRENT_GENERATION_RECONCILED',
                'source_ref': 'core/integration',
                'source_commit': 'a' * 40,
                'credential_exposed': False,
                'reconnected': True,
            }

        def receipt(self, task_id):
            raise AssertionError('read-only reconnect must not poll node receipt endpoint')

    github = FakeGitHub([_comment(310, command)])
    one = ReconnectOne()
    bridge = ControlInboxBridge(
        _config(tmp_path, actions={'node.runtime.converge.inspect'}),
        github=github,
        one=one,
    )
    assert bridge.process_once() == 1
    assert len(one.dispatched) == 1
    assert github.results[0]['status'] == 'completed'
    assert github.results[0]['task_id'] == 'action-existing-123'
    projected = github.results[0]['receipt']
    assert projected['classification'] == 'CURRENT_GENERATION_RECONCILED'
    assert projected['source_commit'] == 'a' * 40
    rendered = json.dumps(github.results[0])
    assert 'original-runtime-request' not in rendered


def test_runtime_converge_inspect_can_be_explicitly_allowlisted(tmp_path: Path):
    config = _config(tmp_path, actions={'node.runtime.converge.inspect'})
    assert config.allowed_actions == frozenset({'node.runtime.converge.inspect'})


def test_generic_execution_action_cannot_be_allowlisted(tmp_path: Path):
    with pytest.raises(ValueError, match='cannot be allowlisted'):
        _config(tmp_path, actions={'shell.exec'})


def test_action_not_in_local_allowlist_is_rejected(tmp_path: Path):
    github = FakeGitHub([_comment(108, _command(action='desktop.session.inspect'))])
    one = FakeOne()
    bridge = ControlInboxBridge(_config(tmp_path, actions={'agent.surface.inspect'}), github=github, one=one)
    assert bridge.process_once() == 1
    assert one.dispatched == []
    assert github.results[0]['status'] == 'rejected'
    assert github.results[0]['error'] == 'unauthorized_action'


def _identity():
    return {
        'schema': 'agentos.continuation-identity/v1', 'source': 'ONE_ACTIVE_CONTINUATION',
        'project_id': 'agentos-core', 'index_id': 'idx-1', 'ir_id': 'ir-1',
        'observed_at': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'canonical_ir_included': False, 'hydration_complete': False, 'credential_exposed': False,
    }


class IdentityOne(FakeOne):
    def __init__(self):
        super().__init__()
        self.reads = 0

    def inspect_continuation(self):
        self.reads += 1
        return {**_identity(), 'canonical_ir': {'goal': 'PRIVATE'}, 'token': 'PRIVATE'}


def test_identity_read_never_dispatches_and_deduplicates_across_restart(tmp_path):
    command = _command(action=CONTINUATION_INSPECT_ACTION)
    command['node_id'] = 'oracle-core-node'
    github = FakeGitHub([_comment(201, command)])
    one = IdentityOne()
    config = _config(tmp_path, actions={CONTINUATION_INSPECT_ACTION})
    assert ControlInboxBridge(config, github=github, one=one).process_once() == 1
    assert ControlInboxBridge(config, github=github, one=one).process_once() == 0
    assert one.reads == 1
    assert one.dispatched == []
    assert github.results[0]['receipt']['hydration_complete'] is False
    assert 'PRIVATE' not in json.dumps(github.results)
    assert 'PRIVATE' not in config.state_path.read_text()


@pytest.mark.parametrize('change', [
    {'args': {'url': 'https://other.invalid'}}, {'args': {'project': 'other'}},
    {'args': []}, {'args': None}, {'node_id': 'node-a'}, {'path': '/private'},
    {'args': {'action': 'shell.exec'}},
])
def test_identity_read_rejects_caller_routing_and_payload(tmp_path, change):
    command = {**_command(action=CONTINUATION_INSPECT_ACTION), 'node_id': 'oracle-core-node', **change}
    github = FakeGitHub([_comment(202, command)])
    one = IdentityOne()
    ControlInboxBridge(_config(tmp_path, actions={CONTINUATION_INSPECT_ACTION}), github=github, one=one).process_once()
    assert github.results[0]['status'] == 'rejected'
    assert one.reads == 0 and one.dispatched == []


@pytest.mark.parametrize('change', [
    {'schema': 'wrong'}, {'source': 'LOCAL_HISTORY'}, {'credential_exposed': True},
    {'canonical_ir_included': True}, {'hydration_complete': True},
    {'ir_id': '/home/private'}, {'index_id': 'x' * 129}, {'project_id': None},
    {'observed_at': '2020-01-01T00:00:00Z'}, {'observed_at': '2026-99-99T00:00:00Z'},
])
def test_identity_client_rejects_malformed_or_stale_evidence(change):
    client = StubOneControllerClient(200, {'ok': True, 'identity': {**_identity(), **change}})
    with pytest.raises(OneControllerError):
        client.inspect_continuation()


def test_identity_client_uses_only_fixed_metadata_endpoint():
    client = StubOneControllerClient(200, {'ok': True, 'identity': _identity(), 'resolution': 'PRIVATE'})
    calls = []
    def request(method, path, payload=None):
        calls.append((method, path, payload))
        return client.status, client.payload
    client._request = request
    result = client.inspect_continuation()
    assert calls == [('GET', '/v1/controller/continuation/active/identity', None)]
    assert 'PRIVATE' not in json.dumps(result)


@pytest.mark.parametrize('status', [401, 404, 409, 500])
def test_identity_read_errors_do_not_leak_or_fall_back(status):
    client = StubOneControllerClient(status, {'debug': 'PRIVATE'})
    with pytest.raises(OneControllerError, match=f'^one_continuation_http_{status}$'):
        client.inspect_continuation()


def test_runtime_converge_receipt_projection_preserves_bounded_diagnostics_only():
    projected = _project_receipt({
        'schema': 'agentos.runtime-converge-receipt/v1',
        'node_id': 'oracle-core-node',
        'task_id': 'action-12345678',
        'action': 'node.runtime.converge',
        'ok': False,
        'repository': 'alston-personal/agentmanager',
        'source_ref': 'core/integration',
        'source_commit': 'a' * 40,
        'previous_commit': 'b' * 40,
        'resulting_commit': 'b' * 40,
        'health': 'failed',
        'rollback': 'completed',
        'classification': 'TARGET_HEALTH_FAILED_ROLLED_BACK',
        'idempotent': False,
        'credential_exposed': False,
        'stdout': 'private output',
        'stderr': '/home/ubuntu/private',
    }, 'node.runtime.converge')
    assert projected['classification'] == 'TARGET_HEALTH_FAILED_ROLLED_BACK'
    assert projected['health'] == 'failed'
    assert projected['rollback'] == 'completed'
    assert projected['source_commit'] == 'a' * 40
    assert projected['previous_commit'] == 'b' * 40
    assert projected['resulting_commit'] == 'b' * 40
    assert projected['idempotent'] is False
    rendered = json.dumps(projected)
    assert 'private output' not in rendered
    assert '/home/ubuntu/private' not in rendered
