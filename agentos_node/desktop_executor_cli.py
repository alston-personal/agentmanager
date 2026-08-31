from __future__ import annotations

import argparse
from pathlib import Path

from agentos_node.desktop_executor_host import DesktopExecutorHost


def main() -> int:
    parser = argparse.ArgumentParser(prog='agentos-desktop-executor')
    parser.add_argument('--bridge', type=Path, required=True)
    parser.add_argument('--poll-seconds', type=float, default=0.2)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('once', help='publish executor state and process queued requests once')
    sub.add_parser('run', help='run the interactive desktop executor host')
    args = parser.parse_args()

    host = DesktopExecutorHost(bridge_root=args.bridge, poll_seconds=args.poll_seconds)
    if args.command == 'once':
        processed = host.serve_once()
        print(f'desktop_executor_processed={processed}')
        return 0
    host.run_forever()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
