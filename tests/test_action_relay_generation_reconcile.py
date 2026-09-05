from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import reconcile_action_relay_runtime as reconcile


SHA = "a" * 40


class Proc(SimpleNamespace):
    returncode: int = 0
    stdout: str = ""
    stderr: str = ""


def _repo(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "agentmanager"
    data = tmp_path / "agent-data"
    (repo / ".git").mkdir(parents=True)
    (repo / "scripts").mkdir(parents=True)
    (repo / "scripts" / "install_action_relay_user.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    (repo / "scripts" / "install_action_relay_reconcile_timer_user.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    return repo, data


def _git_current(monkeypatch):
    def fake_git_value(repo, *args):
        if args[:2] == ("status", "--porcelain"):
            return ""
        if args == ("rev-parse", "HEAD"):
            return SHA
        if args == ("rev-parse", "FETCH_HEAD"):
            return SHA
        raise AssertionError(args)

    monkeypatch.setattr(reconcile, "_git_value", fake_git_value)


def _write_marker(data: Path) -> None:
    marker = data / "runtime" / "action-relay" / "capabilities.json"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps({
        "schema": reconcile.MARKER_SCHEMA,
        "source_ref": reconcile.SOURCE_REF,
        "source_commit": SHA,
        "actions": ["agentos.runtime.converge"],
        "node_capabilities": ["node.runtime.converge"],
    }), encoding="utf-8")


def test_current_marker_service_and_timer_do_not_reinstall(monkeypatch, tmp_path):
    repo, data = _repo(tmp_path)
    _git_current(monkeypatch)
    _write_marker(data)
    calls = []

    def fake_run(argv, *, cwd, env=None, timeout=120):
        calls.append(list(argv))
        if argv[:3] == ["git", "fetch", "--no-tags"]:
            return Proc(returncode=0)
        raise AssertionError(argv)

    monkeypatch.setattr(reconcile, "_run", fake_run)
    monkeypatch.setattr(reconcile, "_service_active", lambda repo: True)
    monkeypatch.setattr(reconcile, "_timer_enabled", lambda repo: True)
    result = reconcile.reconcile(repo=repo, data_root=data)
    assert result["status"] == "current"
    assert result["reconcile_timer_enabled"] is True
    assert result["reconcile_timer_installed"] is False
    assert calls == [["git", "fetch", "--no-tags", "origin", "core/integration"]]


def test_current_generation_bootstraps_missing_independent_timer(monkeypatch, tmp_path):
    repo, data = _repo(tmp_path)
    _git_current(monkeypatch)
    _write_marker(data)
    timer_states = iter([False, True])
    calls = []

    def fake_run(argv, *, cwd, env=None, timeout=120):
        calls.append((list(argv), dict(env or {})))
        if argv[:3] == ["git", "fetch", "--no-tags"]:
            return Proc(returncode=0)
        if argv == ["bash", str(repo / "scripts" / "install_action_relay_reconcile_timer_user.sh")]:
            return Proc(returncode=0)
        raise AssertionError(argv)

    monkeypatch.setattr(reconcile, "_run", fake_run)
    monkeypatch.setattr(reconcile, "_service_active", lambda repo: True)
    monkeypatch.setattr(reconcile, "_timer_enabled", lambda repo: next(timer_states))
    result = reconcile.reconcile(repo=repo, data_root=data)
    assert result["status"] == "current"
    assert result["reconcile_timer_installed"] is True
    timer_call, timer_env = calls[-1]
    assert timer_call == ["bash", str(repo / "scripts" / "install_action_relay_reconcile_timer_user.sh")]
    assert timer_env["AGENTOS_REPO"] == str(repo)
    assert timer_env["AGENT_DATA_ROOT"] == str(data)


def test_generation_drift_runs_fixed_relay_installer_then_ensures_timer(monkeypatch, tmp_path):
    repo, data = _repo(tmp_path)
    _git_current(monkeypatch)
    calls = []

    def fake_run(argv, *, cwd, env=None, timeout=120):
        calls.append((list(argv), dict(env or {})))
        if argv[:3] == ["git", "fetch", "--no-tags"]:
            return Proc(returncode=0)
        if argv == ["bash", str(repo / "scripts" / "install_action_relay_user.sh")]:
            _write_marker(data)
            return Proc(returncode=0)
        if argv == ["bash", str(repo / "scripts" / "install_action_relay_reconcile_timer_user.sh")]:
            return Proc(returncode=0)
        raise AssertionError(argv)

    timer_states = iter([False, True])
    monkeypatch.setattr(reconcile, "_run", fake_run)
    monkeypatch.setattr(reconcile, "_service_active", lambda repo: True)
    monkeypatch.setattr(reconcile, "_timer_enabled", lambda repo: next(timer_states))
    result = reconcile.reconcile(repo=repo, data_root=data)
    assert result["status"] == "reconciled"
    relay_argv, relay_env = calls[1]
    assert relay_argv == ["bash", str(repo / "scripts" / "install_action_relay_user.sh")]
    assert relay_env["AGENTOS_ACTION_SOURCE_REF"] == "core/integration"
    assert relay_env["AGENTOS_ACTION_SOURCE_COMMIT"] == SHA
    assert relay_env["AGENTOS_REPO"] == str(repo)
    assert relay_env["AGENT_DATA_ROOT"] == str(data)
    timer_argv, _ = calls[-1]
    assert timer_argv == ["bash", str(repo / "scripts" / "install_action_relay_reconcile_timer_user.sh")]


def test_reexec_enters_only_fixed_agentos_group_and_exact_script(monkeypatch, tmp_path):
    script = tmp_path / "scripts" / "reconcile_action_relay_runtime.py"
    script.parent.mkdir(parents=True)
    script.write_text("# test\n", encoding="utf-8")
    monkeypatch.setattr(reconcile, "_in_shared_group", lambda: False)
    monkeypatch.setattr(reconcile, "__file__", str(script))
    seen = {}

    def fake_subprocess_run(argv, *, cwd, env, check):
        seen["argv"] = list(argv)
        seen["cwd"] = cwd
        seen["env"] = dict(env)
        return Proc(returncode=7)

    monkeypatch.setattr(reconcile.subprocess, "run", fake_subprocess_run)
    rc = reconcile._reexec_in_shared_group()
    assert rc == 7
    assert seen["argv"][:3] == ["/usr/bin/sg", "agentos", "-c"]
    assert str(script) in seen["argv"][3]
    assert seen["env"][reconcile.GROUP_REEXEC_GUARD] == "1"


def test_reexec_guard_fails_closed_if_agentos_group_still_unavailable(monkeypatch):
    monkeypatch.setattr(reconcile, "_in_shared_group", lambda: False)
    monkeypatch.setenv(reconcile.GROUP_REEXEC_GUARD, "1")
    with pytest.raises(RuntimeError, match="agentos_group_unavailable"):
        reconcile._reexec_in_shared_group()


def test_reconciler_refuses_checkout_not_equal_to_current_core_integration(monkeypatch, tmp_path):
    repo, data = _repo(tmp_path)

    def fake_git_value(repo, *args):
        if args[:2] == ("status", "--porcelain"):
            return ""
        if args == ("rev-parse", "HEAD"):
            return "b" * 40
        if args == ("rev-parse", "FETCH_HEAD"):
            return SHA
        raise AssertionError(args)

    monkeypatch.setattr(reconcile, "_git_value", fake_git_value)
    monkeypatch.setattr(reconcile, "_run", lambda argv, **kwargs: Proc(returncode=0) if argv[:3] == ["git", "fetch", "--no-tags"] else (_ for _ in ()).throw(AssertionError(argv)))
    with pytest.raises(RuntimeError, match="checkout_not_current_core_integration"):
        reconcile.reconcile(repo=repo, data_root=data)


def test_timer_installer_has_fixed_group_context_and_no_caller_execution_surface():
    source = (Path(__file__).resolve().parents[1] / "scripts" / "install_action_relay_reconcile_timer_user.sh").read_text(encoding="utf-8")
    assert "/usr/bin/sg agentos -c" in source
    assert "reconcile_action_relay_runtime.py" in source
    assert "OnUnitActiveSec=5min" in source
    assert "Persistent=true" in source
    assert "systemctl --user enable --now agentos-action-relay-reconcile.timer" in source
    assert "systemctl --user start agentos-action-relay-reconcile.service" not in source


def test_maintenance_keeps_transitional_core_only_reconcile_fallback():
    source = (Path(__file__).resolve().parents[1] / "scripts" / "maintenance.py").read_text(encoding="utf-8")
    assert 'AGENT_MODE' in source
    assert '== "CORE"' in source
    assert 'run_script("reconcile_action_relay_runtime.py")' in source
