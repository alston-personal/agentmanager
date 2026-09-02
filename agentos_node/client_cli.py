from __future__ import annotations

import argparse
import json
import os
import socket
import sys
from pathlib import Path
from typing import Any

from agentos_node.onboarding import check_windows_node_supervisor, install_windows_node_supervisor
from agentos_node.thin_client import NodeIdentity, ThinClient, ThinClientPolicy, render_json
from agentos_node.thin_client_transport import ClientConfig, ThinClientTransport, build_client


_RUN_MUTEX_HANDLE: object | None = None


def _acquire_run_guard(node_id: str) -> bool:
    """Keep one persistent Thin Client daemon per Windows node identity."""
    if os.name != 'nt':
        return True
    import ctypes
    from ctypes import wintypes

    global _RUN_MUTEX_HANDLE
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    create_mutex = kernel32.CreateMutexW
    create_mutex.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    create_mutex.restype = wintypes.HANDLE
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = [wintypes.HANDLE]
    close_handle.restype = wintypes.BOOL

    name = 'Local\\AgentOS-ThinClient-' + ''.join(ch if ch.isalnum() or ch in '._-' else '_' for ch in node_id)
    handle = create_mutex(None, False, name)
    if not handle:
        raise OSError(ctypes.get_last_error(), 'CreateMutexW failed')
    if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
        close_handle(handle)
        return False
    _RUN_MUTEX_HANDLE = handle
    return True


def _default_config() -> Path:
    root = os.environ.get('AGENTOS_CLIENT_HOME')
    if root:
        return Path(root) / 'client.json'
    return Path.home() / '.agentos' / 'client.json'


def _default_policy() -> Path:
    root = os.environ.get('AGENTOS_CLIENT_HOME')
    if root:
        return Path(root) / 'policy.json'
    return Path.home() / '.agentos' / 'policy.json'


def _absolute_policy_path(value: str | Path, field: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise ValueError(f'{field}_must_be_absolute')
    return path.resolve()


def _load_policy(path: Path) -> ThinClientPolicy:
    if not path.exists():
        raise FileNotFoundError(f'policy file not found: {path}; run `agentos-client policy-init` first')
    data = json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(data, dict):
        raise ValueError('client_policy_must_be_object')
    wake_raw = data.get('employee_wake_root')
    if wake_raw is not None and not isinstance(wake_raw, str):
        raise ValueError('employee_wake_root_must_be_string_or_null')
    wake_root = None if wake_raw in (None, '') else _absolute_policy_path(wake_raw, 'employee_wake_root')
    return ThinClientPolicy(
        allowed_executables=set(data.get('allowed_executables') or []),
        readable_roots=tuple(Path(p) for p in (data.get('readable_roots') or [])),
        writable_roots=tuple(Path(p) for p in (data.get('writable_roots') or [])),
        employee_wake_root=wake_root,
        max_timeout_seconds=int(data.get('max_timeout_seconds') or 300),
    )


def _save_default_policy(
    path: Path,
    root: str | None = None,
    employee_wake_root: str | Path | None = None,
) -> None:
    workspace = str(Path(root or Path.home() / 'AgentOS').expanduser().resolve())
    wake_root = None
    if employee_wake_root is not None and str(employee_wake_root) != '':
        wake_root = str(_absolute_policy_path(str(employee_wake_root), 'employee_wake_root'))
    payload = {
        'schema': 'agentos.client-policy/v0.1',
        'allowed_executables': ['git', 'python', 'python.exe', 'python3', 'powershell', 'powershell.exe', 'pwsh', 'cmd', 'cmd.exe'],
        'readable_roots': [workspace],
        'writable_roots': [workspace],
        'employee_wake_root': wake_root,
        'max_timeout_seconds': 120,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog='agentos-client')
    parser.add_argument('--config', type=Path, default=_default_config())
    parser.add_argument('--policy', type=Path, default=_default_policy())
    sub = parser.add_subparsers(dest='command', required=True)

    p_policy = sub.add_parser('policy-init', help='create a conservative local execution policy')
    p_policy.add_argument('--root', help='workspace root ONE may read/write')
    p_policy.add_argument(
        '--employee-wake-root',
        help='absolute local inbox root for governed Employee wake delivery; omitted means capability disabled',
    )

    p_join = sub.add_parser('join', help='join Realm, install lifecycle supervisor, bootstrap inherited cognition, run regression, become ready')
    p_join.add_argument('--one', required=True, help='ONE base URL')
    p_join.add_argument('--node-id', default=socket.gethostname().lower())
    p_join.add_argument('--expires-minutes', type=int, default=10)
    p_join.add_argument('--timeout-seconds', type=int, default=600)

    p_enroll = sub.add_parser('enroll', help='legacy one-time invitation enrollment')
    p_enroll.add_argument('--one', required=True, help='ONE base URL')
    p_enroll.add_argument('--invite-id', required=True)
    p_enroll.add_argument('--code', required=True)
    p_enroll.add_argument('--node-id', default=socket.gethostname().lower())

    sub.add_parser('manifest', help='print local capability manifest')
    sub.add_parser('health', help='check ONE health')
    sub.add_parser('bootstrap', help='show inherited Realm capabilities and canonical capability states')
    sub.add_parser('verify', help='verify an already-enrolled Node including lifecycle supervisor and persist regression evidence')
    sub.add_parser('once', help='heartbeat, refresh discovery, pull tasks once, execute, return receipts')
    sub.add_parser('run', help='run persistent polling daemon')
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == 'policy-init':
        try:
            _save_default_policy(args.policy, args.root, args.employee_wake_root)
        except ValueError as exc:
            print(f'error: {exc}', file=sys.stderr)
            return 2
        return 0

    policy = _load_policy(args.policy)

    if args.command == 'join':
        before_manifest = ThinClient(NodeIdentity('pending', args.node_id), policy).capability_manifest()

        def show_request(payload: dict[str, object]) -> None:
            print('AgentOS enrollment approval required')
            print(f'Node: {payload.get("node_id")}')
            print(f'Code: {payload.get("user_code")}')
            print(f'Expires: {payload.get("expires_at")}')
            print('Tell your Realm administrator or AgentOS assistant to approve this code.')

        def show_status(payload: dict[str, Any]) -> None:
            print(f'[agentos-client] enrollment status: {payload.get("status")}', flush=True)

        config = ThinClientTransport.enroll_device(
            one_url=args.one,
            node_id=args.node_id,
            policy=policy,
            config_path=args.config,
            expires_minutes=args.expires_minutes,
            timeout_seconds=args.timeout_seconds,
            on_request=show_request,
            on_status=show_status,
        )
        lifecycle = install_windows_node_supervisor()
        transport = build_client(config, policy)
        completion = transport.complete_join(before_manifest, lifecycle=lifecycle)
        print(render_json({'ok': bool(completion.get('node_ready')), 'realm_id': config.realm_id, 'node_id': config.node_id, 'config': str(args.config), 'lifecycle': lifecycle, 'completion': completion}))
        return 0 if completion.get('node_ready') else 2

    if args.command == 'enroll':
        config = ThinClientTransport.enroll(one_url=args.one, invite_id=args.invite_id, code=args.code, node_id=args.node_id, policy=policy, config_path=args.config)
        print(render_json({'ok': True, 'realm_id': config.realm_id, 'node_id': config.node_id, 'config': str(args.config)}))
        return 0

    config = ClientConfig.load(args.config)
    if args.command == 'run' and not _acquire_run_guard(config.node_id):
        print(f'[agentos-client] another daemon already owns node identity: {config.node_id}', flush=True)
        return 3
    transport = build_client(config, policy)
    if args.command == 'manifest':
        print(render_json(transport.client.capability_manifest()))
    elif args.command == 'health':
        print(render_json(transport.health()))
    elif args.command == 'bootstrap':
        print(render_json(transport.bootstrap()))
    elif args.command == 'verify':
        lifecycle = check_windows_node_supervisor()
        readiness = transport.verify_readiness(lifecycle=lifecycle)
        print(render_json({'ok': bool(readiness.get('node_ready')), 'lifecycle': lifecycle, 'readiness': readiness}))
        return 0 if readiness.get('node_ready') else 2
    elif args.command == 'once':
        print(render_json({'receipts': transport.run_once()}))
    elif args.command == 'run':
        transport.run_forever()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
