import subprocess
from pathlib import Path
from unittest import mock

from agentos_node.thin_client import NodeIdentity, ThinClient, ThinClientPolicy


def _client():
    return ThinClient(
        NodeIdentity('realm-test', 'oracle-exec'),
        ThinClientPolicy(readable_roots=(Path('/tmp'),)),
    )


def test_runner_inspect_discovers_only_github_runner_units():
    client = _client()

    def fake_run(argv, **kwargs):
        if argv[:2] == ['systemctl', 'list-units']:
            return subprocess.CompletedProcess(
                argv, 0,
                stdout=(
                    'actions.runner.alston-personal-agentmanager.instance.service loaded active running Runner\n'
                    'ssh.service loaded active running SSH\n'
                ),
                stderr='',
            )
        if argv[:2] == ['systemctl', 'is-active']:
            return subprocess.CompletedProcess(argv, 0, stdout='active\n', stderr='')
        raise AssertionError(argv)

    with mock.patch('agentos_node.thin_client.platform.system', return_value='Linux'), \
         mock.patch('agentos_node.thin_client.subprocess.run', side_effect=fake_run):
        result = client._inspect_runner()

    assert result == {
        'runner_unit_count': 1,
        'runner_active_count': 1,
        'runner_failed_count': 0,
        'runner_healthy': True,
    }


def test_runner_recover_restarts_only_discovered_runner_unit():
    client = _client()
    calls = []

    def fake_run(argv, **kwargs):
        calls.append(argv)
        if argv[:2] == ['systemctl', 'list-units']:
            return subprocess.CompletedProcess(
                argv, 0,
                stdout='actions.runner.repo.node.service loaded active running Runner\n',
                stderr='',
            )
        if argv[:2] == ['systemctl', 'is-active']:
            return subprocess.CompletedProcess(argv, 0, stdout='active\n', stderr='')
        if 'restart' in argv:
            assert argv[-1] == 'actions.runner.repo.node.service'
            return subprocess.CompletedProcess(argv, 0, stdout='', stderr='')
        raise AssertionError(argv)

    with mock.patch('agentos_node.thin_client.platform.system', return_value='Linux'), \
         mock.patch('agentos_node.thin_client.os.geteuid', return_value=0), \
         mock.patch('agentos_node.thin_client.subprocess.run', side_effect=fake_run):
        result = client._recover_runner()

    assert result['recovered'] is True
    assert result['restart_attempted_count'] == 1
    assert result['restart_failed_count'] == 0
    assert not any('ssh.service' in part for call in calls for part in call)
