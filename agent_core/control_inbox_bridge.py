from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


COMMAND_SCHEMA = 'agentos.control-command/v0.1'
RESULT_SCHEMA = 'agentos.control-result/v0.1'
STATE_SCHEMA = 'agentos.control-inbox-state/v0.2'
LEGACY_STATE_SCHEMA = 'agentos.control-inbox-state/v0.1'
DEFAULT_REPOSITORY = 'alston-personal/agentmanager'
DEFAULT_ISSUE_NUMBER = 50
DEFAULT_ALLOWED_LOGIN = 'alstonhuang'
DEFAULT_ONE_URL = 'http://127.0.0.1:8780'
MAX_COMMAND_LIFETIME_SECONDS = 600
FORBIDDEN_ACTION_PREFIXES = (
    'shell.', 'filesystem.', 'fs.', 'keyboard.', 'mouse.',
    'gui.input', 'desktop.input',
)
COMMON_RECEIPT_FIELDS = (
    'schema', 'node_id', 'task_id', 'action', 'ok', 'realm_id',
    'received_at', 'started_at', 'completed_at', 'status', 'state',
)


class OneControllerError(RuntimeError):
    """Safe ONE error containing only a stable classification code."""


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


def _is_forbidden_action(action: str) -> bool:
    value = str(action or '').strip().lower()
    return any(value.startswith(prefix) for prefix in FORBIDDEN_ACTION_PREFIXES)


def _safe_scalar(value: Any) -> Any:
    if isinstance(value, (bool, int, float)) or value is None:
        return value
    if isinstance(value, str):
        # Receipts are evidence, not a secret-bearing debug channel.  Keep bounded
        # scalar protocol data only; never echo authorization/token-like strings.
        lowered = value.lower()
        if any(marker in lowered for marker in ('bearer ', 'github_pat_', 'ghp_', 'token=', 'secret=')):
            return '<redacted>'
        return value[:256]
    return None


def _project_surface_inventory(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    projected: dict[str, Any] = {}
    for key in ('schema', 'surface_count', 'capabilities', 'providers'):
        item = value.get(key)
        if isinstance(item, list):
            projected[key] = [str(v)[:128] for v in item[:64] if isinstance(v, (str, int, float, bool))]
        elif isinstance(item, (str, int, float, bool)):
            projected[key] = _safe_scalar(item)
    surfaces = []
    for surface in value.get('surfaces') or []:
        if not isinstance(surface, dict):
            continue
        safe = {}
        for key in ('surface_id', 'provider', 'kind', 'running', 'attachable', 'capabilities'):
            item = surface.get(key)
            if isinstance(item, list):
                safe[key] = [str(v)[:128] for v in item[:32] if isinstance(v, (str, int, float, bool))]
            elif isinstance(item, (str, int, float, bool)) or item is None:
                safe[key] = _safe_scalar(item)
        surfaces.append(safe)
    if surfaces:
        projected['surfaces'] = surfaces[:64]
    return projected


def _project_receipt(receipt: Any, action: str) -> dict[str, Any] | None:
    """Return bounded evidence; drop paths, usernames, titles and raw payloads."""
    if not isinstance(receipt, dict):
        return None
    projected: dict[str, Any] = {}
    for key in COMMON_RECEIPT_FIELDS:
        if key in receipt:
            safe = _safe_scalar(receipt.get(key))
            if safe is not None or receipt.get(key) is None:
                projected[key] = safe

    if action == 'agent.surface.inspect':
        inventory = _project_surface_inventory(receipt.get('surface_inventory'))
        if inventory is not None:
            projected['surface_inventory'] = inventory
    elif action == 'desktop.session.inspect':
        desktop = receipt.get('desktop')
        if isinstance(desktop, dict):
            projected['desktop'] = {
                key: _safe_scalar(desktop.get(key))
                for key in ('interactive', 'active_console_session_id', 'process_session_id')
                if key in desktop
            }
    elif action == 'desktop.windows.inspect':
        if isinstance(receipt.get('window_count'), int):
            projected['window_count'] = receipt['window_count']
        # Window titles and usernames are intentionally not published to GitHub.
        processes = []
        for window in receipt.get('windows') or []:
            if isinstance(window, dict) and isinstance(window.get('process_name'), str):
                processes.append(window['process_name'][:128])
        if processes:
            projected['processes'] = sorted(set(processes))[:64]
    return projected


@dataclass(frozen=True)
class BridgeConfig:
    repository: str
    issue_number: int
    allowed_login: str
    allowed_actions: frozenset[str]
    github_token: str
    controller_token: str
    one_url: str
    state_path: Path
    poll_seconds: float
    receipt_wait_seconds: int

    def __post_init__(self) -> None:
        if not self.allowed_login:
            raise ValueError('allowed login is required')
        if not self.allowed_actions:
            raise ValueError('explicit control action allowlist is required')
        if any(_is_forbidden_action(action) for action in self.allowed_actions):
            raise ValueError('generic shell/filesystem/input action cannot be allowlisted')

    @classmethod
    def from_env(cls) -> 'BridgeConfig':
        github_token = str(os.environ.get('AGENTOS_GITHUB_TOKEN') or os.environ.get('GH_TOKEN') or '').strip()
        controller_token = str(os.environ.get('AGENTOS_CONTROLLER_TOKEN') or '').strip()
        allowed_actions = frozenset(
            value.strip()
            for value in str(os.environ.get('AGENTOS_CONTROL_ALLOWED_ACTIONS') or '').split(',')
            if value.strip()
        )
        if not github_token:
            raise RuntimeError('AGENTOS_GITHUB_TOKEN or GH_TOKEN is required')
        if not controller_token:
            raise RuntimeError('AGENTOS_CONTROLLER_TOKEN is required')
        if not allowed_actions:
            raise RuntimeError('AGENTOS_CONTROL_ALLOWED_ACTIONS is required')
        data_root = Path(os.environ.get('AGENT_DATA_ROOT', '/home/ubuntu/agent-data'))
        return cls(
            repository=str(os.environ.get('AGENTOS_CONTROL_REPOSITORY') or DEFAULT_REPOSITORY),
            issue_number=int(os.environ.get('AGENTOS_CONTROL_ISSUE') or DEFAULT_ISSUE_NUMBER),
            allowed_login=str(os.environ.get('AGENTOS_CONTROL_ALLOWED_LOGIN') or DEFAULT_ALLOWED_LOGIN),
            allowed_actions=allowed_actions,
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
                'User-Agent': 'AgentOS-Control-Inbox/0.2',
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
                try:
                    body = json.loads(raw) if raw else None
                except json.JSONDecodeError as exc:
                    raise OneControllerError('one_protocol_invalid_json') from exc
                return int(response.status), body
        except HTTPError as exc:
            # Never read or echo ONE's error body. It can contain internal details.
            return int(exc.code), None
        except (URLError, TimeoutError, OSError) as exc:
            raise OneControllerError('one_unavailable') from exc

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
        if not 200 <= status < 300:
            raise OneControllerError(f'one_dispatch_http_{status}')
        if not isinstance(payload, dict) or payload.get('ok') is not True:
            raise OneControllerError('one_dispatch_protocol_error')
        return payload

    def receipt(self, task_id: str) -> dict[str, Any] | None:
        status, payload = self._request('GET', f'/v1/controller/receipts/{task_id}')
        if status == 404:
            return None
        if not 200 <= status < 300:
            raise OneControllerError(f'one_receipt_http_{status}')
        if not isinstance(payload, dict) or payload.get('ok') is not True:
            raise OneControllerError('one_receipt_protocol_error')
        receipt = payload.get('receipt')
        return receipt if isinstance(receipt, dict) else None


class ControlInboxBridge:
    def __init__(self, config: BridgeConfig, *, github: GitHubIssueClient | None = None, one: OneControllerClient | None = None):
        self.config = config
        self.github = github or GitHubIssueClient(config.repository, config.issue_number, config.github_token)
        self.one = one or OneControllerClient(config.one_url, config.controller_token)

    def _load_state(self) -> dict[str, Any]:
        if not self.config.state_path.exists():
            return {'schema': STATE_SCHEMA, 'processed_comment_ids': [], 'commands': {}}
        data = json.loads(self.config.state_path.read_text(encoding='utf-8'))
        schema = data.get('schema')
        if schema not in {STATE_SCHEMA, LEGACY_STATE_SCHEMA}:
            raise ValueError('invalid control inbox state')
        data['schema'] = STATE_SCHEMA
        data.setdefault('processed_comment_ids', [])
        data.setdefault('commands', {})
        return data

    def _save_state(self, state: dict[str, Any]) -> None:
        self.config.state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.config.state_path.with_suffix('.tmp')
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')
        tmp.replace(self.config.state_path)

    def _validate_command(self, payload: dict[str, Any]) -> dict[str, Any]:
        if payload.get('schema') != COMMAND_SCHEMA:
            raise ValueError('invalid_command_schema')
        command_id = str(payload.get('command_id') or '').strip()
        node_id = str(payload.get('node_id') or '').strip()
        action = str(payload.get('action') or '').strip()
        try:
            issued_at = _parse_utc(str(payload.get('issued_at') or ''))
            expires_at = _parse_utc(str(payload.get('expires_at') or ''))
        except (TypeError, ValueError) as exc:
            raise ValueError('invalid_command_time') from exc
        now = _utc_now()
        if not command_id or not node_id or not action:
            raise ValueError('missing_command_identity')
        if action not in self.config.allowed_actions or _is_forbidden_action(action):
            raise ValueError('unauthorized_action')
        if issued_at > now + timedelta(seconds=60):
            raise ValueError('issued_at_in_future')
        if expires_at <= now:
            raise ValueError('command_expired')
        if expires_at <= issued_at:
            raise ValueError('invalid_expiry_window')
        if (expires_at - issued_at).total_seconds() > MAX_COMMAND_LIFETIME_SECONDS:
            raise ValueError('command_lifetime_exceeds_limit')
        args = payload.get('args') or {}
        if not isinstance(args, dict):
            raise ValueError('invalid_args')
        return {
            'schema': COMMAND_SCHEMA,
            'command_id': command_id,
            'issued_at': _iso(issued_at),
            'expires_at': _iso(expires_at),
            'node_id': node_id,
            'action': action,
            'args': args,
        }

    def _result(self, command: dict[str, Any], *, status: str,
                task_id: str | None = None, receipt: dict[str, Any] | None = None,
                error: str | None = None) -> dict[str, Any]:
        result: dict[str, Any] = {
            'schema': RESULT_SCHEMA,
            'command_id': str(command.get('command_id') or 'unknown')[:160],
            'node_id': str(command.get('node_id') or 'unknown')[:160],
            'action': str(command.get('action') or 'unknown')[:160],
            'status': status,
            'observed_at': _iso(),
        }
        if task_id:
            result['task_id'] = task_id[:160]
        if receipt is not None:
            projected = _project_receipt(receipt, result['action'])
            if projected is not None:
                result['receipt'] = projected
        if error:
            result['error'] = str(error)[:160]
        return result

    def _terminal(self, state: dict[str, Any], command_id: str,
                  result: dict[str, Any], *, posted: bool = False) -> None:
        state['commands'][command_id] = {
            'phase': 'terminal', 'result': result, 'posted': posted, 'updated_at': _iso(),
        }
        self._save_state(state)

    def _flush_pending(self, state: dict[str, Any]) -> int:
        posted = 0
        for command_id, entry in list(state.get('commands', {}).items()):
            if not isinstance(entry, dict):
                continue
            if entry.get('phase') == 'claimed':
                # We cannot know whether ONE executed after a crash. Never redispatch.
                command = entry.get('command') if isinstance(entry.get('command'), dict) else {'command_id': command_id}
                result = self._result(command, status='unknown', error='bridge_interrupted_after_claim')
                self._terminal(state, command_id, result, posted=False)
                entry = state['commands'][command_id]
            if entry.get('phase') == 'terminal' and not entry.get('posted'):
                result = entry.get('result')
                if isinstance(result, dict):
                    self.github.post_result(result)
                    entry['posted'] = True
                    entry['updated_at'] = _iso()
                    self._save_state(state)
                    posted += 1
        return posted

    def process_once(self) -> int:
        state = self._load_state()
        self._flush_pending(state)
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
                state['processed_comment_ids'] = sorted(processed)[-2000:]
                self._save_state(state)
                continue

            command_id = str(payload.get('command_id') or f'comment:{comment_id}')
            if command_id in state['commands']:
                processed.add(comment_id)
                state['processed_comment_ids'] = sorted(processed)[-2000:]
                self._save_state(state)
                continue

            try:
                command = self._validate_command(payload)
            except ValueError as exc:
                result = self._result(payload, status='rejected', error=str(exc))
                processed.add(comment_id)
                state['processed_comment_ids'] = sorted(processed)[-2000:]
                self._terminal(state, command_id, result, posted=False)
                self.github.post_result(result)
                state['commands'][command_id]['posted'] = True
                self._save_state(state)
                handled += 1
                continue

            # Persist the privileged boundary before dispatch. A restart after this
            # point becomes `unknown`; it never silently replays the command.
            processed.add(comment_id)
            state['processed_comment_ids'] = sorted(processed)[-2000:]
            state['commands'][command_id] = {
                'phase': 'claimed', 'command': command, 'claimed_at': _iso(),
            }
            self._save_state(state)

            try:
                dispatch = self.one.dispatch(command['node_id'], command)
                task_id = str(dispatch.get('task_id') or _task_id(command_id))
                deadline = time.monotonic() + self.config.receipt_wait_seconds
                receipt = None
                while time.monotonic() < deadline:
                    receipt = self.one.receipt(task_id)
                    if receipt is not None:
                        break
                    time.sleep(1)
                status = 'completed' if receipt is not None else 'queued'
                result = self._result(command, status=status, task_id=task_id, receipt=receipt)
            except OneControllerError as exc:
                result = self._result(command, status='error', error=str(exc))
            except Exception:
                # Deliberately do not serialize exception text: unexpected exceptions
                # can contain headers, paths, args or backend payloads.
                result = self._result(command, status='error', error='bridge_internal_error')

            self._terminal(state, command_id, result, posted=False)
            self.github.post_result(result)
            state['commands'][command_id]['posted'] = True
            self._save_state(state)
            handled += 1
        return handled

    def run_forever(self) -> None:
        while True:
            try:
                self.process_once()
            except Exception:
                # Keep the daemon alive without echoing secret-bearing exceptions.
                print('control_inbox_bridge_error=cycle_failed', flush=True)
            time.sleep(self.config.poll_seconds)


def main() -> int:
    bridge = ControlInboxBridge(BridgeConfig.from_env())
    bridge.run_forever()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
