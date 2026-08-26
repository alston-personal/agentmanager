from __future__ import annotations

import argparse
import json
from pathlib import Path

from agent_core.node_registry import NodeRegistry
from agent_core.realm_fabric import RealmFabricStore
from agent_core.realm_server import serve


def _print(payload: object) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def main() -> int:
    parser = argparse.ArgumentParser(prog='agentos-one')
    sub = parser.add_subparsers(dest='command', required=True)

    p_init = sub.add_parser('init')
    p_init.add_argument('--realm-id', required=True)

    p_invite = sub.add_parser('invite')
    p_invite.add_argument('--minutes', type=int, default=10)
    p_invite.add_argument('--label')

    p_serve = sub.add_parser('serve')
    p_serve.add_argument('--host', default='127.0.0.1')
    p_serve.add_argument('--port', type=int, default=8765)

    p_task = sub.add_parser('task')
    p_task.add_argument('--node-id', required=True)
    p_task.add_argument('--task-file', type=Path, required=True)

    p_receipt = sub.add_parser('receipt')
    p_receipt.add_argument('--task-id', required=True)

    sub.add_parser('nodes')

    args = parser.parse_args()
    fabric = RealmFabricStore()

    if args.command == 'init':
        _print(fabric.initialize_realm(args.realm_id))
    elif args.command == 'invite':
        _print(fabric.create_invite(expires_minutes=args.minutes, label=args.label))
    elif args.command == 'serve':
        serve(host=args.host, port=args.port, fabric=fabric)
    elif args.command == 'task':
        task = json.loads(args.task_file.read_text(encoding='utf-8'))
        _print(fabric.queue_task(args.node_id, task))
    elif args.command == 'receipt':
        _print(fabric.get_receipt(args.task_id))
    elif args.command == 'nodes':
        _print(NodeRegistry().node_map())
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
