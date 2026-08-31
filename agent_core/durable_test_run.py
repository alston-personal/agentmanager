from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
import json
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


class TestRunState(str, Enum):
    CREATED = 'created'
    PREFLIGHT = 'preflight'
    READY = 'ready'
    RUNNING = 'running'
    WAITING_OFFLINE = 'waiting_offline'
    WAITING_ONLINE = 'waiting_online'
    RECOVERING = 'recovering'
    PASSED = 'passed'
    FAILED = 'failed'
    ABORTED = 'aborted'


TERMINAL_STATES = {TestRunState.PASSED, TestRunState.FAILED, TestRunState.ABORTED}


@dataclass
class TestCheckpoint:
    name: str
    state: str
    observed_at: str = field(default_factory=utc_now)
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class DurableTestRun:
    run_id: str
    scenario: str
    node_ids: list[str]
    state: TestRunState = TestRunState.CREATED
    current_step: str | None = None
    expected_offline_nodes: list[str] = field(default_factory=list)
    reconnect_deadline: str | None = None
    recovery_plans: dict[str, dict[str, Any]] = field(default_factory=dict)
    checkpoints: list[TestCheckpoint] = field(default_factory=list)
    receipts: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    verdict: str | None = None
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        if not self.run_id or not self.scenario:
            raise ValueError('run_id and scenario are required')
        if not self.node_ids:
            raise ValueError('at least one node_id is required')

    def transition(self, state: TestRunState, *, step: str | None = None, details: dict[str, Any] | None = None) -> None:
        if self.state in TERMINAL_STATES:
            raise RuntimeError(f'cannot transition terminal test run: {self.state.value}')
        self.state = state
        if step is not None:
            self.current_step = step
        self.updated_at = utc_now()
        self.checkpoints.append(TestCheckpoint(name=step or state.value, state=state.value, details=details or {}))

    def arm_recovery(self, node_id: str, plan: dict[str, Any]) -> None:
        if node_id not in self.node_ids:
            raise ValueError(f'node is not part of test run: {node_id}')
        if not plan.get('action') or not plan.get('expires_at'):
            raise ValueError('recovery plan requires action and expires_at')
        self.recovery_plans[node_id] = dict(plan)
        self.updated_at = utc_now()
        self.checkpoints.append(TestCheckpoint(name='recovery_armed', state=self.state.value, details={'node_id': node_id, 'action': plan['action'], 'expires_at': plan['expires_at']}))

    def expect_offline(self, node_id: str, *, reconnect_deadline: str) -> None:
        if node_id not in self.recovery_plans:
            raise RuntimeError('cannot expect node offline before recovery is armed')
        if node_id not in self.expected_offline_nodes:
            self.expected_offline_nodes.append(node_id)
        self.reconnect_deadline = reconnect_deadline
        self.transition(TestRunState.WAITING_OFFLINE, step='expect_offline', details={'node_id': node_id, 'reconnect_deadline': reconnect_deadline})

    def observe_online(self, node_id: str, *, boot_id: str | None = None) -> None:
        if node_id in self.expected_offline_nodes:
            self.expected_offline_nodes.remove(node_id)
        details: dict[str, Any] = {'node_id': node_id}
        if boot_id:
            details['boot_id'] = boot_id
        self.transition(TestRunState.RUNNING, step='node_online', details=details)

    def finish(self, passed: bool, verdict: str) -> None:
        self.state = TestRunState.PASSED if passed else TestRunState.FAILED
        self.verdict = verdict
        self.updated_at = utc_now()
        self.checkpoints.append(TestCheckpoint(name='finish', state=self.state.value, details={'verdict': verdict}))

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload['state'] = self.state.value
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> 'DurableTestRun':
        data = dict(payload)
        data['state'] = TestRunState(data.get('state', TestRunState.CREATED.value))
        data['checkpoints'] = [TestCheckpoint(**item) for item in data.get('checkpoints', [])]
        return cls(**data)


class JsonTestRunStore:
    def __init__(self, root: Path):
        self.root = root.expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, run_id: str) -> Path:
        safe = ''.join(ch for ch in run_id if ch.isalnum() or ch in {'-', '_'})
        if safe != run_id or not safe:
            raise ValueError('unsafe run_id')
        return self.root / f'{safe}.json'

    def save(self, run: DurableTestRun) -> Path:
        path = self._path(run.run_id)
        tmp = path.with_suffix('.json.tmp')
        tmp.write_text(json.dumps(run.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')
        tmp.replace(path)
        return path

    def load(self, run_id: str) -> DurableTestRun | None:
        path = self._path(run_id)
        if not path.is_file():
            return None
        return DurableTestRun.from_dict(json.loads(path.read_text(encoding='utf-8')))
