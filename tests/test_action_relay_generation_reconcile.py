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


def test_current_marker_and_service_do_not_reinstall(monkeypatch, tmp_path):
    repo, data = _repo(tmp_path)
    _git_current(monkeypatch)
    marker = data / "runtime" / "action-relay" / "capabilities.json"
    marker.parent.mkdir(parents=True)
    marker.write_text(json.dumps({
        "schema": reconcile.MARKER_SCHEMA,
        "source_ref": reconcile.SOURCE_REF,
        "source_commit": SHA,
        "actions": ["agentos.runtime.converge"],
        "node_capabilities": ["node.runtime.converge"],
    }), encoding="utf-8")
    calls = []

    def fake_run(argv, *, cwd, env=None, timeout=120):
        calls.append(list(argv))
        if argv[:3] == ["git", "fetch", "--no-tags"]:
            return Proc(returncode=0)
        raise AssertionError(argv)

    monkeypatch.setattr(reconcile, "_run", fake_run)
    monkeypatch.setattr(reconcile, "_service_active", lambda repo: True)
    result = reconcile.reconcile(repo=repo, data_root=data)
    assert result["status"] == "current"
    assert calls == [["git", "fetch", "--no-tags", "origin", "core/integration"]]


def test_generation_drift_runs_only_fixed_installer_with_exact_generation(monkeypatch, tmp_path):
    repo, data = _repo(tmp_path)
    _git_current(monkeypatch)
    calls = []

    def fake_run(argv, *, cwd, env=None, timeout=120):
        calls.append((list(argv), dict(env or {})))
        if argv[:3] == ["git", "fetch", "--no-tags"]:
            return Proc(returncode=0)
        if argv[0] == "bash":
            marker = data / "runtime" / "action-relay" / "capabilities.json"
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text(json.dumps({
                "schema": reconcile.MARKER_SCHEMA,
                "source_ref": reconcile.SOURCE_REF,
                "source_commit": SHA,
                "actions": ["agentos.runtime.converge"],
                "node_capabilities": ["node.runtime.converge"],
            }), encoding="utf-8")
            return Proc(returncode=0)
        raise AssertionError(argv)

    monkeypatch.setattr(reconcile, "_run", fake_run)
    monkeypatch.setattr(reconcile, "_service_active", lambda repo: True)
    result = reconcile.reconcile(repo=repo, data_root=data)
    assert result["status"] == "reconciled"
    install_argv, install_env = calls[-1]
    assert install_argv == ["bash", str(repo / "scripts" / "install_action_relay_user.sh")]
    assert install_env["AGENTOS_ACTION_SOURCE_REF"] == "core/integration"
    assert install_env["AGENTOS_ACTION_SOURCE_COMMIT"] == SHA
    assert install_env["AGENTOS_REPO"] == str(repo)
    assert install_env["AGENT_DATA_ROOT"] == str(data)


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


def test_maintenance_invokes_generation_reconciler_only_on_core_profile():
    source = (Path(__file__).resolve().parents[1] / "scripts" / "maintenance.py").read_text(encoding="utf-8")
    assert 'AGENT_MODE' in source
    assert '== "CORE"' in source
    assert 'run_script("reconcile_action_relay_runtime.py")' in source
