#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from agent_core.platform import get_platform_driver, normalize_platform_name


def main() -> int:
    parser = argparse.ArgumentParser(description="AgentOS platform runtime helper")
    parser.add_argument("--platform", dest="platform", default=None, help="Override platform selection")
    parser.add_argument("--project-root", default=None)
    parser.add_argument("--data-root", default=None)
    subparsers = parser.add_subparsers(dest="command", required=True)

    info = subparsers.add_parser("info", help="Print runtime paths and selected platform")

    install = subparsers.add_parser("install-services", help="Install background services for the current platform")

    service = subparsers.add_parser("service", help="Manage a named service")
    service.add_argument("action", choices=["start", "stop", "restart"])
    service.add_argument("name")

    job = subparsers.add_parser("schedule", help="Register a recurring job")
    job.add_argument("name")
    job.add_argument("interval_seconds", type=int)
    job.add_argument("cmd_parts", nargs=argparse.REMAINDER)

    args = parser.parse_args()

    driver = get_platform_driver(
        platform_name=args.platform,
        project_root=Path(args.project_root) if getattr(args, "project_root", None) else None,
        data_root=Path(args.data_root) if getattr(args, "data_root", None) else None,
    )

    if args.command == "info":
        print(
            json.dumps(
                {
                    "platform": driver.platform_name(),
                    "runtime_dir": str(driver.runtime_dir()),
                    "volatile_state_dir": str(driver.volatile_state_dir()),
                    "persistent_state_dir": str(driver.persistent_state_dir()),
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0

    if args.command == "install-services":
        result = driver.install_background_services()
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    if args.command == "service":
        action = getattr(args, "action")
        method = getattr(driver, f"{action}_service")
        result = method(args.name)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    if args.command == "schedule":
        command = args.cmd_parts if args.cmd_parts else []
        result = driver.schedule_recurring_job(args.name, command, args.interval_seconds)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
