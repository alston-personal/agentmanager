from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen


COMMAND_SCHEMA = 'agentos.control-command/v0.1'
RESULT_SCHEMA = 'agentos.control-result/v0.1'
DEFAULT_REPOSITORY = 'alston-personal/agentmanager'
DEFAULT_ISSUE_NUMBER = 50
DEFAULT_ALLOWED_LOGIN = 'alstonhuang'
DEFAULT_ONE_URL = 'http://127.0.0.1:8780'
MAX_COMMAND_LIFETIME_SECONDS = 600
CONTROLLER_DISPATCH_SUCCESS_CODES = frozenset({200, 202})


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime | None = None) -> str:
    return (dt or _utc_now()).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(str(value).replace('Z', '+00:00')).astimezone(timezone.utc)


def _json_from_comment(body: str) -> dict[str, Any] | None:
    text = str(body or '').strip()
    if text.startswith('```') and text.endswith('```'):
        lines = text.splitlines()
        if len(lines) >= 3:
            text = '\n'.join(lines[1:-1]).strip()
    try:
        payload = json.loads(text)
    except (TypeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _task_id(command_id: str) -> str:
    digest = hashlib.sha256(command_id.encode('utf-8')).hexdigest()[:24]
    return 'ctl_' + digest


@dataclass(frozen=True)
class BridgeConfig:
    repository: str
    issue_number: int
    allowed_login: str
    github_token: str
    controller_token: str
    one_url: str
    state_path: Path
    poll_seconds: float
    receipt_wait_seconds: int

    @classmethod
    def from_env(cls) -> 'BridgeConfig':
        github_token = str(os.environ.get('AGENTOS_GITHUB_TOKEN') or os.environ.get('GH_TOKEN') or '').strip()
        controller_token = str(os.environ.get('AGENTOS_CONTROLLER_TOKEN') or '').strip()
        if not github_token:
            raise RuntimeError('AGENTOS_GITHUB_TOKEN or GH_TOKEN is required')
        if not controller_token:
            raise RuntimeError('AGENTOS_CONTROLLER_TOKEN is required')
        data_root = Path(os.environ.get('AGENT_DATA_ROOT', '/home/ubuntu/agent-data'))
        return cls(
            repository=str(os.environ.get('AGENTOS_CONTROL_REPOSITORY') or DEFAULT_REPOSITORY),
            issue_number=int(os.environ.get('AGENTOS_CONTROL_ISSUE') or DEFAULT_ISSUE_NUMBER),
            allowed_login=str(os.environ.get('AGENTOS_CONTROL_ALLOWED_LOGIN') or DEFAULT_ALLOWED_LOGIN),
            github_token=github_token,
            controller_token=controller_token,
            one_url=str(os.environ.get('AGENTOS_ONE_URL') or DEFAULT_ONE_URL).rstrip('/'),
            state_path=Path(os.environ.get('AGENTOS_CONTROL_STATE') or data_root / 'runtime' / 'control-inbox' / 'state.json'),
            poll_seconds=max(1.0, float(os.environ.get('AGENTOS_CONTROL_POLL_SECONDS') or 3)),
            receipt_wait_seconds=max(1, min(120, int(os.environ.get('AGENTOS_CONTROL_RECEIPT_WAIT_SECONDS') or 45))),
        )


class GitHubIssueClient:
    def __init__(self, repository: str, issue_number: int, token: str):
        self.repository = repository
        self.issue_number = issue_number
        self.token = token

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        data = None if payload is None else json.dumps(payload).encode('utf-8')
        request = Request(
            'https://api.github.com' + path,
            data=data,
            method=method,
            headers={
                'Accept': 'application/vnd.github+json',
                'Authorization': f'Bearer {self.token}',
                'X-GitHub-Api-Version': '2022-11-28',
                'User-Agent': 'AgentOS-Control-Inbox/0.1',
                'Content-Type': 'application/json',
            },
        )
        with urlopen(request, timeout=15) as response:
            raw = response.read().decode('utf-8')
            return json.loads(raw) if raw else None

    def comments(self) -> list[dict[str, Any]]:
        comments: list[dict[str, Any]] = []
        page = 1
        while True:
            batch = self._request(
                'GET',
                f'/repos/{self.repository}/issues/{self.issue_number}/comments?per_page=100&page={page}&sort=created&direction=asc',
            )
            if not isinstance(batch, list):
                raise RuntimeError('GitHub comments response must be a list')
            comments.extend(item for item in batch if isinstance(item, dict))
            if len(batch) < 100:
                break
            page += 1
        return comments

    def post_result(self, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        self._request(
            'POST',
            f'/repos/{self.repository}/issues/{self.issue_number}/comments',
            {'body': body},
        )


class OneControllerClient:
    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip('/')
        self.token = token

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> tuple[int, Any]:
        data = None if payload is None else json.dumps(payload).encode('utf-8')
        request = Request(
            self.base_url + path,
            data=data,
            method=method,
            headers={
                'Authorization': f'Bearer {self.token}',
                'Accept': 'application/json',
                'Content-Type': 'application/json',
            },
        )
        try:
            with urlopen(request, timeout=10) as response:
                raw = response.read().decode('utf-8')
                return int(response.status), json.loads(raw) if raw else None
        except HTTPError as exc:
            raw = exc.read().decode('utf-8')
            try:
                body = json.loads(raw) if raw else None
            except json.JSONDecodeError:
                body = {'error': raw}
            return int(exc.code), body

    def dispatch(self, node_id: str, command: dict[str, Any]) -> dict[str, Any]:
        args = command.get('args') or {}
        if not isinstance(args, dict):
            raise ValueError('args must be an object')
        body = {
            'node_id': node_id,
            'task_id': _task_id(str(command['command_id'])),
            'action': command['action'],
            **args,
        }
        status, payload = self._request('POST', '/v1/controller/dispatch', body)
        if status not in CONTROLLER_DISPATCH_SUCCESS_CODES or not isinstance(payload, dict) or not payload.get('ok'):
            raise RuntimeError(f'ONE dispatch failed: HTTP {status}: {payload}')
        return payload

    def receipt(self, task_id: str) -> dict[str, Any] | None:
        status, payload = self._request('GET', f'/v1/controller/receipts/{task_id}')
        if status == 404:
            return None
        if status != 200 or not isinstance(payload, dict) or not payload.get('ok'):
            raise RuntimeError(f'ONE receipt failed: HTTP {status}: {payload}')
        receipt = payload.get('receipt')
        return receipt if isinstance(receipt, dict) else None


class ControlInboxBridge:
    def __init__(self, config: BridgeConfig, *, github: GitHubIssueClient | None = None, one: OneControllerClient | None = None):
        self.config = config
        self.github = github or GitHubIssueClient(config.repository, config.issue_number, config.github_token)
        self.one = one or OneControllerClient(config.one_url, config.controller_token)

    def _load_state(self) -> dict[str, Any]:
        if not self.config.state_path.exists():
            return {'schema': 'agentos.control-inbox-state/v0.1', 'processed_comment_ids': []}
        data = json.loads(self.config.state_path.read_text(encoding='utf-8'))
        if data.get('schema') != 'agentos.control-inbox-state/v0.1':
            raise ValueError('invalid control inbox state')
        data.setdefault('processed_comment_ids', [])
        return data

    def _save_state(self, state: dict[str, Any]) -> None:
        self.config.state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.config.state_path.with_suffix('.tmp')
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')
        tmp.replace(self.config.state_path)

    def _validate_command(self, payload: dict[str, Any]) -> dict[str, Any]:
        if payload.get('schema') != COMMAND_SCHEMA:
            raise ValueError('invalid command schema')
        command_id = str(payload.get('command_id') or '').strip()
        node_id = str(payload.get('node_id') or '').strip()
        action = str(payload.get('action') or '').strip()
        issued_at = _parse_utc(str(payload.get('issued_at') or ''))
        expires_at = _parse_utc(str(payload.get('expires_at') or ''))
        now = _utc_now()
        if not command_id or not node_id or not action:
            raise ValueError('command_id, node_id and action are required')
        if issued_at > now + timedelta(seconds=60):
            raise ValueError('issued_at is in the future')
        if expires_at <= now:
            raise ValueError('command expired')
        if expires_at <= issued_at:
            raise ValueError('expires_at must be after issued_at')
        if (expires_at - issued_at).total_seconds() > MAX_COMMAND_LIFETIME_SECONDS:
            raise ValueError('command lifetime exceeds bootstrap limit')
        args = payload.get('args') or {}
        if not isinstance(args, dict):
            raise ValueError('args must be an object')
        return {
            'schema': COMMAND_SCHEMA,
            'command_id': command_id,
            'issued_at': _iso(issued_at),
            'expires_at': _iso(expires_at),
            'node_id': node_id,
            'action': action,
            'args': args,
        }

    def _result(self, command: dict[str, Any], *, status: str, task_id: str | None = None, receipt: dict[str, Any] | None = None, error: str | None = None) -> dict[str, Any]:
        result: dict[str, Any] = {
            'schema': RESULT_SCHEMA,
            'command_id': command.get('command_id'),
            'node_id': command.get('node_id'),
            'action': command.get('action'),
            'status': status,
            'observed_at': _iso(),
        }
        if task_id:
            result['task_id'] = task_id
        if receipt is not None:
            result['receipt'] = receipt
        if error:
            result['error'] = error
        return result

    def process_once(self) -> int:
        state = self._load_state()
        processed = {int(value) for value in state.get('processed_comment_ids') or []}
        handled = 0
        for comment in self.github.comments():
            comment_id = int(comment.get('id') or 0)
            if not comment_id or comment_id in processed:
                continue
            author = str((comment.get('user') or {}).get('login') or '')
            payload = _json_from_comment(str(comment.get('body') or ''))
            if author != self.config.allowed_login or payload is None or payload.get('schema') != COMMAND_SCHEMA:
                processed.add(comment_id)
                continue

            command: dict[str, Any] = payload
            try:
                command = self._validate_command(payload)
                dispatch = self.one.dispatch(command['node_id'], command)
                task_id = str(dispatch.get('task_id') or '')
                deadline = time.monotonic() + self.config.receipt_wait_seconds
                receipt = None
                while time.monotonic() < deadline:
                    receipt = self.one.receipt(task_id)
                    if receipt is not None:
                        break
                    time.sleep(1)
                status = 'completed' if receipt is not None else 'queued'
                self.github.post_result(self._result(command, status=status, task_id=task_id, receipt=receipt))
            except Exception as exc:
                self.github.post_result(self._result(command, status='error', error=f'{type(exc).__name__}: {exc}'))

            processed.add(comment_id)
            handled += 1
            state['processed_comment_ids'] = sorted(processed)[-1000:]
            state['updated_at'] = _iso()
            self._save_state(state)
        return handled

    def run_forever(self) -> None:
        while True:
            try:
                self.process_once()
            except Exception as exc:
                print(f'control_inbox_bridge_error={type(exc).__name__}: {exc}', flush=True)
            time.sleep(self.config.poll_seconds)


def main() -> int:
    bridge = ControlInboxBridge(BridgeConfig.from_env())
    bridge.run_forever()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
