from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import time
from typing import Callable


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


@dataclass(frozen=True)
class RecoveryLease:
    lease_id: str
    action: str
    expires_at_epoch: int
    command: tuple[str, ...]
    created_at: str = ''

    def __post_init__(self) -> None:
        if not self.lease_id or not self.action:
            raise ValueError('lease_id and action are required')
        if self.expires_at_epoch <= int(time.time()):
            raise ValueError('recovery lease must expire in the future')
        if not self.command:
            raise ValueError('recovery command is required')
        if not self.created_at:
            object.__setattr__(self, 'created_at', utc_now())

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload['command'] = list(self.command)
        return payload

    @classmethod
    def from_dict(cls, payload: dict) -> 'RecoveryLease':
        data = dict(payload)
        data['command'] = tuple(data['command'])
        return cls(**data)


class RecoveryLeaseStore:
    def __init__(self, root: Path):
        self.root = root.expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, lease_id: str) -> Path:
        safe = ''.join(ch for ch in lease_id if ch.isalnum() or ch in {'-', '_'})
        if safe != lease_id or not safe:
            raise ValueError('unsafe lease_id')
        return self.root / f'{safe}.json'

    def arm(self, lease: RecoveryLease) -> Path:
        path = self.path_for(lease.lease_id)
        tmp = path.with_suffix('.json.tmp')
        tmp.write_text(json.dumps(lease.to_dict(), indent=2, sort_keys=True) + '\n', encoding='utf-8')
        tmp.replace(path)
        return path

    def disarm(self, lease_id: str) -> None:
        path = self.path_for(lease_id)
        if path.exists():
            path.unlink()

    def load(self, lease_id: str) -> RecoveryLease | None:
        path = self.path_for(lease_id)
        if not path.is_file():
            return None
        return RecoveryLease.from_dict(json.loads(path.read_text(encoding='utf-8')))


def execute_due_recovery(
    lease: RecoveryLease,
    *,
    now_epoch: int | None = None,
    runner: Callable[[tuple[str, ...]], int] | None = None,
) -> bool:
    now = int(time.time()) if now_epoch is None else int(now_epoch)
    if now < lease.expires_at_epoch:
        return False
    if runner is None:
        def runner(command: tuple[str, ...]) -> int:
            completed = subprocess.run(list(command), check=False, timeout=60)
            return int(completed.returncode)
    rc = runner(lease.command)
    if rc != 0:
        raise RuntimeError(f'recovery command failed: rc={rc}')
    return True


@dataclass(frozen=True)
class UpdatePlan:
    source_ref: str
    install_root: str
    files: tuple[str, ...]
    restart_command: tuple[str, ...]

    def __post_init__(self) -> None:
        if len(self.source_ref) != 40 or any(ch not in '0123456789abcdef' for ch in self.source_ref.lower()):
            raise ValueError('source_ref must be an immutable 40-character commit SHA')
        if not self.files or not self.restart_command:
            raise ValueError('update plan requires files and restart command')


class IndependentUpdater:
    """Contract for an updater process that is not the daemon being replaced.

    The daemon may request an update, but a separate process/service must stage files,
    verify them, stop the old daemon, atomically install, restart, and report status.
    """

    def __init__(self, *, current_pid: int, updater_pid: int):
        if current_pid == updater_pid:
            raise ValueError('updater must be a different process from the daemon')
        self.current_pid = current_pid
        self.updater_pid = updater_pid

    def validate_plan(self, plan: UpdatePlan) -> None:
        root = Path(plan.install_root).expanduser()
        if not root.is_absolute():
            raise ValueError('install_root must be absolute')
        for rel in plan.files:
            path = Path(rel)
            if path.is_absolute() or '..' in path.parts:
                raise ValueError(f'unsafe update path: {rel}')
