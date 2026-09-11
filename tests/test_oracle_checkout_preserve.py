import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import oracle_checkout_preserve as preservation
sys.path.pop(0)


@pytest.fixture
def checkout(tmp_path):
    root = tmp_path / 'repo'
    root.mkdir()
    def git(*args):
        return subprocess.check_output(['git', '-C', str(root), *args], stderr=subprocess.DEVNULL).decode().strip()
    git('init')
    git('config', 'user.name', 'Test')
    git('config', 'user.email', 'test@example.invalid')
    git('remote', 'add', 'origin', 'https://github.com/alston-personal/agentmanager.git')
    (root / 'scripts').mkdir()
    (root / '.secrets.baseline').write_text('{"results":{}}')
    (root / 'scripts/detect_secrets_scanner.py').write_text('x = 1\n')
    git('add', '.')
    git('commit', '-m', 'fixture')
    (root / '.secrets.baseline').write_text('{"results":{"PRIVATE":[{"secret":"DO_NOT_EXPORT"}]}}')
    git('add', '.secrets.baseline')
    (root / 'scripts/detect_secrets_scanner.py').write_text('x = 2\n')
    expected = {p:preservation.digest((root / p).read_bytes()) for p in preservation.EXPECTED}
    return root, expected, git('rev-parse', 'HEAD')


def test_private_backup_preserves_index_and_worktree(checkout, tmp_path):
    root, expected, head = checkout
    originals = {p:(root / p).read_bytes() for p in [*expected, '.git/index']}
    target = tmp_path / 'private' / 'backup'
    report = preservation.preserve(root, target, expected, head)
    assert report['backup_verified']
    assert not report['automatic_recovery_safe']
    assert 'PRIVATE' not in json.dumps(report) and 'DO_NOT_EXPORT' not in json.dumps(report)
    assert report['review'][0]['index_equals_worktree']
    assert not report['review'][1]['python_ast_equal']
    assert report['review'][0]['new_finding_count'] == 1
    assert target.stat().st_mode & 0o777 == 0o700
    assert all(p.stat().st_mode & 0o777 == 0o600 for p in target.iterdir())
    assert (target / 'git-index.bin').read_bytes() == originals['.git/index']
    for p, data in originals.items():
        assert (root / p).read_bytes() == data
    with pytest.raises(FileExistsError):
        preservation.preserve(root, target, expected, head)
    assert (target / 'manifest.json').is_file()


def test_stale_hash_refuses_before_backup(checkout, tmp_path):
    root, expected, head = checkout
    expected['scripts/detect_secrets_scanner.py'] = '0' * 64
    target = tmp_path / 'backup'
    with pytest.raises(ValueError):
        preservation.preserve(root, target, expected, head)
    assert not target.exists()


def test_backup_symlink_refused(checkout, tmp_path):
    root, expected, head = checkout
    real = tmp_path / 'real'
    real.mkdir()
    link = tmp_path / 'link'
    link.symlink_to(real)
    with pytest.raises(OSError):
        preservation.preserve(root, link / 'backup', expected, head)
    assert not list(real.iterdir())
