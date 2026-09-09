import importlib.util
import json
from pathlib import Path
import subprocess

SPEC = importlib.util.spec_from_file_location('diagnostic', Path(__file__).resolve().parents[1] / 'scripts/oracle_checkout_diagnostic.py')
diagnostic = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(diagnostic)


def test_real_checkout_diagnostic_preserves_unknown_changes(tmp_path):
    def git(*args):
        return subprocess.check_output(['git', '-C', str(tmp_path), *args], stderr=subprocess.DEVNULL).decode().strip()
    git('init')
    git('config', 'user.name', 'Test')
    git('config', 'user.email', 'test@example.invalid')
    git('remote', 'add', 'origin', 'https://github.com/alston-personal/agentmanager.git')
    file = tmp_path / 'source.py'
    file.write_text('original')
    git('add', 'source.py')
    git('commit', '-m', 'fixture')
    file.write_text('PRIVATE_BODY_DO_NOT_EXPORT')
    before_index = (tmp_path / '.git/index').read_bytes()
    report = diagnostic.inspect(tmp_path)
    assert report['dirty_tracked'] is True
    assert report['automatic_recovery_safe'] is False
    assert report['paths'][0]['path'] == 'source.py'
    assert 'PRIVATE_BODY' not in json.dumps(report)
    assert report['paths'][0]['equals_target_blob'] is None
    assert file.read_text() == 'PRIVATE_BODY_DO_NOT_EXPORT'
    assert (tmp_path / '.git/index').read_bytes() == before_index
    assert report['status_stable_during_read'] is True


def test_symlink_content_not_read(tmp_path, monkeypatch):
    outside = tmp_path / 'outside'
    outside.write_text('PRIVATE')
    (tmp_path / 'link').symlink_to(outside)
    def git(root, *args):
        if args[0] == 'remote':
            return 'https://github.com/alston-personal/agentmanager.git'
        if args[0] == 'status':
            return ' M link\0'
        return 'a' * 40
    monkeypatch.setattr(diagnostic, 'git', git)
    report = diagnostic.inspect(tmp_path)
    assert report['paths'][0]['hash_omitted'] == 'not_regular_or_symlink'
    assert 'PRIVATE' not in json.dumps(report)


def test_public_paths_are_bounded():
    for path in ('../secret', '/secret', 'x\nsecret', 'x' * 257):
        assert not diagnostic.safe_path(path)
