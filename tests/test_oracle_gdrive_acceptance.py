#!/usr/bin/env python3
"""Hermetic contract tests for read-only GDrive acceptance; never connect to Oracle."""
import os
import pathlib
import subprocess
import tempfile
from datetime import datetime, timezone

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / 'scripts' / 'oracle_gdrive_acceptance.sh'

def check(fail_command=None, health_state="READY", stale=False, wrong_symlink=False):
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        home = root / 'home'
        bin_dir = root / 'bin'
        bin_dir.mkdir()
        canonical = home / '.local/share/agentos/gdrive-remote-v2'
        (canonical / 'backups').mkdir(parents=True)
        (home / '.local/state/agentos').mkdir(parents=True)
        now = '2020-01-01T00:00:00Z' if stale else datetime.now(timezone.utc).isoformat()
        (home / '.local/state/agentos/gdrive-health.state').write_text(f'checked_at={now}\nstate={health_state}\n')
        (home / 'gdrive').symlink_to(home if wrong_symlink else canonical)
        commands = {
            'mountpoint': '#!/bin/sh\nexit 0\n',
            'findmnt': '#!/bin/sh\necho fuse.rclone\n',
            'rclone': '#!/bin/sh\nexit 0\n',
            'systemctl': '#!/bin/sh\nexit 0\n',
            'ls': '#!/bin/sh\nexit 0\n',
        }
        if fail_command:
            commands[fail_command] = '#!/bin/sh\nexit 1\n'
        for name, body in commands.items():
            p = bin_dir / name
            p.write_text(body)
            p.chmod(0o755)
        env = dict(os.environ, HOME=str(home), PATH=str(bin_dir) + ':' + os.environ['PATH'])
        result = subprocess.run(['bash', str(SCRIPT)], capture_output=True, text=True, env=env, timeout=15)
        expected = 42 if fail_command or stale or wrong_symlink or health_state != "READY" else 0
        assert result.returncode == expected, (fail_command, result.returncode, result.stdout, result.stderr)
        assert f'oracle_gdrive_read_acceptance={"FAIL" if expected else "PASS"}' in result.stdout
        assert 'gdrive_underlay_writer_protection=UNVERIFIED' in result.stdout
        assert 'secret' not in result.stdout.lower()
        return result.stdout

if __name__ == '__main__':
    check()
    for name in ['mountpoint','findmnt','rclone','systemctl','ls']:
        check(name)
    check(stale=True)
    check(wrong_symlink=True)
    check(health_state='FAILED')
    print('acceptance_contract_tests=PASS cases=9')
