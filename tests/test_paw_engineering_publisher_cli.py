from pathlib import Path
from types import SimpleNamespace

import pytest

import agentos_node.paw_engineering_publisher_cli as cli
from agentos_node.paw_engineering_worktree import PawWorktreeBoundaryError


def test_publisher_cli_denies_absent_identity_before_transport(tmp_path, monkeypatch):
    def forbidden(**kwargs):
        raise AssertionError("publisher invoked without identity")
    monkeypatch.setattr(cli, "publish_durable_paw_handoff", forbidden)
    with pytest.raises(PawWorktreeBoundaryError, match="identity_missing"):
        cli.publish_once(
            runtime_root=tmp_path / "runtime",
            workspace_root=tmp_path / "worktrees",
            generation=1, environment={},
        )


def test_publisher_cli_reports_external_draft_without_false_acceptance(tmp_path, monkeypatch):
    captured = []
    def publisher(**kwargs):
        captured.append(kwargs)
        return SimpleNamespace(
            schema="agentos.paw-draft-publication-receipt/v1",
            work_id="issue-470-a", commit_sha="b" * 40,
            pr_number=2099,
            pr_url="https://github.com/alston-personal/agentmanager/pull/2099",
        )
    monkeypatch.setattr(cli, "publish_durable_paw_handoff", publisher)
    result = cli.publish_once(
        runtime_root=tmp_path / "runtime",
        workspace_root=tmp_path / "worktrees",
        generation=1, environment={"GH_TOKEN": "test-only"},
    )
    assert len(captured) == 1
    assert captured[0]["authenticated_publisher"] is True
    assert result["status"] == "published_draft"
    assert result["merged"] is False
    assert result["independent_acceptance_pass"] is False


def test_publisher_cli_requires_absolute_roots(tmp_path):
    with pytest.raises(PawWorktreeBoundaryError, match="absolute_roots_required"):
        cli.publish_once(
            runtime_root=Path("relative"), workspace_root=tmp_path,
            generation=1, environment={"GH_TOKEN": "test-only"},
        )

def test_latest_publisher_idle_without_terminal_receipt(tmp_path):
    assert cli.publish_latest(runtime_root=tmp_path, workspace_root=tmp_path)["status"] == "idle"

def test_latest_publisher_advances_after_persisting_publication(tmp_path, monkeypatch):
    directory = tmp_path / "lifecycle/receipts/paw-470-inspection-v1"
    directory.mkdir(parents=True)
    for name in ("000002.json", "000010.json", "invalid.json"):
        (directory / name).write_text(__import__("json").dumps({"outcome": "handoff", "result_summary": {"bounded_stage": "paw-authorized-local-commit", "commit_sha": "b" * 40}}))
    generations = []
    def publish(**kwargs):
        generations.append(kwargs["generation"])
        return {"status": "published_draft", "commit_sha": "b" * 40}
    monkeypatch.setattr(cli, "publish_once", publish)
    result = cli.publish_latest(runtime_root=tmp_path, workspace_root=tmp_path)
    assert result["status"] == "published_draft"
    assert generations == [2]
    assert (tmp_path / "paw-publications/000002.json").is_file()
    cli.publish_latest(runtime_root=tmp_path, workspace_root=tmp_path)
    assert generations == [2, 10]


def test_oracle_publisher_installer_uses_accepted_venv_and_never_activates_worker():
    root = Path(__file__).resolve().parents[1]
    installer = (root / "scripts/install_paw_publisher_oracle.sh").read_text()
    service = (root / ".agent/scripts/agentos-paw-publisher.service").read_text()
    activation = (root / "scripts/activate_product_employees_oracle.sh").read_text()
    assert 'paw_publisher_release_python_missing' in installer
    assert 's|/usr/bin/python3|$RELEASE/.venv/bin/python3|g' in installer
    assert 'systemctl enable --now agentos-paw-publisher.timer' in installer
    assert all("systemctl --user" not in line for line in installer.splitlines() if not line.lstrip().startswith("#"))
    assert "agentos-paw-publisher" not in activation
    assert "EnvironmentFile=/etc/agentos/paw-publisher.env" in service
    assert "User=agentos-publisher" in service
    assert "Group=agentos-publisher" in service
    assert "User=root" not in service
    assert "paw_publisher_service_user_missing" in installer
    assert "paw_publisher_source_access_missing" in installer
    assert "CapabilityBoundingSet=\n" in service
    assert "AmbientCapabilities=\n" in service
    assert "NoNewPrivileges=true" in service
    assert "UMask=0077" in service
    assert "RestrictSUIDSGID=true" in service
    assert "ReadWritePaths=/home/ubuntu/agent-data/employee-runtime" in service
    assert "ReadOnlyPaths=/home/ubuntu/agent-data/employee-runtime" not in service

def test_publisher_lock_prevents_overlapping_passes(tmp_path):
    with cli._publication_lock(tmp_path):
        with pytest.raises(PawWorktreeBoundaryError, match='already_running'):
            with cli._publication_lock(tmp_path):
                pass
    with cli._publication_lock(tmp_path):
        pass

def test_publisher_lock_releases_after_failure(tmp_path):
    with pytest.raises(RuntimeError, match='failure'):
        with cli._publication_lock(tmp_path):
            raise RuntimeError('failure')
    with cli._publication_lock(tmp_path):
        pass


def test_publisher_never_executes_repository_push_hooks():
    root = Path(__file__).resolve().parents[1]
    source = (root / 'agentos_node/paw_engineering_gh_transport.py').read_text()
    assert '"-c", "core.hooksPath=/dev/null", "push"' in source


def test_publisher_rejects_git_environment_injection(tmp_path, monkeypatch):
    from agentos_node.paw_engineering_gh_transport import publish_with_trusted_gh
    from agentos_node.paw_engineering_commit import PawLocalCommitReceipt
    import agentos_node.paw_engineering_gh_transport as transport
    monkeypatch.setattr(transport, '_git', lambda *args: {'symbolic-ref': 'paw/470/issue-470-a', 'rev-parse': 'b' * 40, 'status': '', 'remote': 'https://github.com/alston-personal/agentmanager.git'}[args[1]])
    monkeypatch.setenv('GIT_CONFIG_COUNT', '1')
    local = PawLocalCommitReceipt(schema='agentos.paw-local-commit-receipt/v1', work_id='issue-470-a', base_sha='a'*40, commit_sha='b'*40, branch='paw/470/issue-470-a', changed_file='tests/test_paw_engineering_worktree.py')
    with pytest.raises(PawWorktreeBoundaryError, match='environment_untrusted'):
        publish_with_trusted_gh(local, worktree=tmp_path, authenticated_publisher=True)


def test_publisher_rejects_divergent_pushurl(tmp_path, monkeypatch):
    from agentos_node.paw_engineering_gh_transport import publish_with_trusted_gh
    from agentos_node.paw_engineering_commit import PawLocalCommitReceipt
    import agentos_node.paw_engineering_gh_transport as transport
    def fake_git(root, *args):
        if args[0] == 'symbolic-ref': return 'paw/470/issue-470-a'
        if args[0] == 'rev-parse': return 'b' * 40
        if args[0] == 'status': return ''
        if args[0] == 'remote' and '--push' in args: return 'https://attacker.invalid/repo.git'
        if args[0] == 'remote': return 'https://github.com/alston-personal/agentmanager.git'
        raise AssertionError(args)
    monkeypatch.setattr(transport, '_git', fake_git)
    local = PawLocalCommitReceipt(schema='agentos.paw-local-commit-receipt/v1', work_id='issue-470-a', base_sha='a'*40, commit_sha='b'*40, branch='paw/470/issue-470-a', changed_file='tests/test_paw_engineering_worktree.py')
    with pytest.raises(PawWorktreeBoundaryError, match='push_target_invalid'):
        publish_with_trusted_gh(local, worktree=tmp_path, authenticated_publisher=True)


def test_publisher_install_preflights_worktree_git_access():
    root = Path(__file__).resolve().parents[1]
    installer = (root / 'scripts/install_paw_publisher_oracle.sh').read_text()
    assert 'paw_publisher_traversal_access_missing' in installer
    assert 'paw_publisher_git_tools_missing' in installer
    assert 'paw_publisher_worktree_git_access_missing' in installer
    assert 'runuser -u agentos-publisher -- git -C "$target" rev-parse --verify HEAD' in installer
