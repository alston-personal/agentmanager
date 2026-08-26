from __future__ import annotations

import argparse
import json
import os
import socket
from pathlib import Path

from agentos_node.thin_client import ThinClientPolicy, render_json
from agentos_node.thin_client_transport import ClientConfig, ThinClientTransport, build_client


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


def _load_policy(path: Path) -> ThinClientPolicy:
    if not path.exists():
        raise FileNotFoundError(f'policy file not found: {path}; run `agentos-client policy-init` first')
    data = json.loads(path.read_text(encoding='utf-8'))
    return ThinClientPolicy(
        allowed_executables=set(data.get('allowed_executables') or []),
        readable_roots=tuple(Path(p) for p in (data.get('readable_roots') or [])),
        writable_roots=tuple(Path(p) for p in (data.get('writable_roots') or [])),
        max_timeout_seconds=int(data.get('max_timeout_seconds') or 300),
    )


def _save_default_policy(path: Path, root: str | None = None) -> None:
    workspace = str(Path(root or Path.home() / 'AgentOS').expanduser().resolve())
    payload = {
        'schema': 'agentos.client-policy/v0.1',
        'allowed_executables': ['git', 'python', 'python.exe', 'python3', 'powershell', 'powershell.exe', 'pwsh', 'cmd', 'cmd.exe'],
        'readable_roots': [workspace],
        'writable_roots': [workspace],
        'max_timeout_seconds': 120,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(path)


def main() -> int:
    parser = argparse.ArgumentParser(prog='agentos-client')
    parser.add_argument('--config', type=Path, default=_default_config())
    parser.add_argument('--policy', type=Path, default=_default_policy())
    sub = parser.add_subparsers(dest='command', required=True)

    p_policy = sub.add_parser('policy-init', help='create a conservative local execution policy')
    p_policy.add_argument('--root', help='workspace root ONE may read/write')

    p_join = sub.add_parser('join', help='request Realm membership and wait for human approval')
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
    sub.add_parser('once', help='heartbeat, pull tasks once, execute, return receipts')
    sub.add_parser('run', help='run persistent polling daemon')

    args = parser.parse_args()

    if args.command == 'policy-init':
        _save_default_policy(args.policy, args.root)
        return 0

    policy = _load_policy(args.policy)

    if args.command == 'join':
        def show_request(payload: dict[str, object]) -> None:
            print('AgentOS enrollment approval required')
            print(f'Node: {payload.get("node_id")}')
            print(f'Code: {payload.get("user_code")}')
            print(f'Expires: {payload.get("expires_at")}')
            print('Tell your Realm administrator or AgentOS assistant to approve this code.')

        def show_status(payload: dict[str, object]) -> None:
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
        print(render_json({'ok': True, 'realm_id': config.realm_id, 'node_id': config.node_id, 'config': str(args.config)}))
        return 0

    if args.command == 'enroll':
        config = ThinClientTransport.enroll(
            one_url=args.one,
            invite_id=args.invite_id,
            code=args.code,
            node_id=args.node_id,
            policy=policy,
            config_path=args.config,
        )
        print(render_json({'ok': True, 'realm_id': config.realm_id, 'node_id': config.node_id, 'config': str(args.config)}))
        return 0

    config = ClientConfig.load(args.config)
    transport = build_client(config, policy)
    if args.command == 'manifest':
        print(render_json(transport.client.capability_manifest()))
    elif args.command == 'health':
        print(render_json(transport.health()))
    elif args.command == 'once':
        print(render_json({'receipts': transport.run_once()}))
    elif args.command == 'run':
        transport.run_forever()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
