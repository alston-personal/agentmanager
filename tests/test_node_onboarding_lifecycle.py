from pathlib import Path

from agentos_node.onboarding import (
    WINDOWS_THIN_CLIENT_TASK,
    WINDOWS_WATCHDOG_TASK,
    build_join_regression_report,
    render_windows_supervisor_install_script,
    render_windows_watchdog_script,
)


def _bootstrap():
    return {
        'schema': 'agentos.node-bootstrap/v0.1',
        'inherited_realm_capabilities': ['shell.exec'],
        'canonical_capabilities': [{'capability_id': 'shell.exec'}],
    }


def test_windows_watchdog_is_independent_and_restarts_thin_client():
    script = render_windows_watchdog_script()
    assert WINDOWS_THIN_CLIENT_TASK in script
    assert 'Get-ScheduledTask' in script
    assert 'Start-ScheduledTask' in script
    assert 'ONE' not in script


def test_windows_supervisor_installs_client_and_watchdog_tasks():
    script = render_windows_supervisor_install_script(
        install_root=Path(r'C:\Users\test\AppData\Local\AgentOS'),
        launcher=Path(r'C:\Users\test\AppData\Local\AgentOS\agentos-client.cmd'),
    )
    assert WINDOWS_THIN_CLIENT_TASK in script
    assert WINDOWS_WATCHDOG_TASK in script
    assert 'Register-ScheduledTask' in script
    assert 'RepetitionInterval (New-TimeSpan -Minutes 1)' in script
    assert 'agentos_supervisor_ready=true' in script


def test_node_ready_requires_supervisor_when_lifecycle_is_supplied():
    manifest = {'capabilities': ['shell.exec'], 'surface_inventory': {}}
    blocked = build_join_regression_report(
        realm_id='realm-test',
        node_id='node-test',
        before_manifest=manifest,
        after_manifest=manifest,
        bootstrap=_bootstrap(),
        lifecycle={'schema': 'agentos.node-lifecycle/v0.1', 'supervisor_ready': False},
    )
    assert blocked['node_ready'] is False
    assert blocked['checks']['lifecycle_supervisor_ready'] is False

    ready = build_join_regression_report(
        realm_id='realm-test',
        node_id='node-test',
        before_manifest=manifest,
        after_manifest=manifest,
        bootstrap=_bootstrap(),
        lifecycle={'schema': 'agentos.node-lifecycle/v0.1', 'supervisor_ready': True},
    )
    assert ready['node_ready'] is True
    assert ready['checks']['lifecycle_supervisor_ready'] is True
