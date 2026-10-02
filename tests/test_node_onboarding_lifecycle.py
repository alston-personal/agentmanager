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
    assert 'heartbeat-lease.json' in script
    assert '$age -gt 120' in script
    assert 'Ensure-AgentOSThinClientTask' in script
    assert 'Register-ScheduledTask' in script
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


def test_linux_supervisor_install_contract(monkeypatch, tmp_path):
    import agentos_node.onboarding as onboarding

    launcher = tmp_path / "agentos-client"
    launcher.write_text("#!/bin/sh\n", encoding="utf-8")
    unit = tmp_path / "agentos-thin-client.service"

    monkeypatch.setattr(onboarding.platform, "system", lambda: "Linux")
    monkeypatch.setattr(onboarding, "linux_thin_client_unit_path", lambda: unit)

    calls = []

    class Result:
        def __init__(self, returncode=0, stdout="", stderr=""):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    def fake_run(argv, **kwargs):
        calls.append(argv)
        if argv[:3] == ["systemctl", "--user", "is-active"]:
            return Result(0, "active\n", "")
        return Result(0, "", "")

    monkeypatch.setattr(onboarding.subprocess, "run", fake_run)
    result = onboarding.install_linux_node_supervisor(install_root=tmp_path, launcher=launcher)

    assert result["supervisor_ready"] is True
    assert unit.exists()
    text = unit.read_text(encoding="utf-8")
    assert "ExecStart=" + str(launcher) + " run" in text
    assert "Restart=always" in text
    assert ["systemctl", "--user", "enable", "--now", "agentos-thin-client.service"] in calls


def test_linux_supervisor_creates_launcher_when_missing(monkeypatch, tmp_path):
    import agentos_node.onboarding as onboarding

    unit = tmp_path / "agentos-thin-client.service"

    monkeypatch.setattr(onboarding.platform, "system", lambda: "Linux")
    monkeypatch.setattr(onboarding, "linux_thin_client_unit_path", lambda: unit)

    class Result:
        def __init__(self, returncode=0, stdout="", stderr=""):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    def fake_run(argv, **kwargs):
        if argv[:3] == ["systemctl", "--user", "is-active"]:
            return Result(0, "active\n", "")
        return Result(0, "", "")

    monkeypatch.setattr(onboarding.subprocess, "run", fake_run)
    result = onboarding.install_linux_node_supervisor(install_root=tmp_path)

    launcher = tmp_path / "agentos-client"
    assert result["supervisor_ready"] is True
    assert launcher.exists()
    assert launcher.stat().st_mode & 0o100
    text = launcher.read_text(encoding="utf-8")
    assert "-m agentos_node.client_cli" in text


def test_linux_supervisor_selected_by_generic_installer(monkeypatch):
    import agentos_node.onboarding as onboarding

    monkeypatch.setattr(onboarding.platform, "system", lambda: "Linux")
    monkeypatch.setattr(onboarding, "install_linux_node_supervisor", lambda: {"supervisor_ready": True, "platform": "Linux"})
    assert onboarding.install_node_supervisor()["platform"] == "Linux"
