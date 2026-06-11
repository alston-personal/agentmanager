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

from agent_core.platform import get_platform_driver


def main() -> int:
    parser = argparse.ArgumentParser(description="Install AgentOS services using the selected platform driver")
    parser.add_argument("--platform", default=None, help="Override platform selection")
    parser.add_argument("--project-root", default=None)
    parser.add_argument("--data-root", default=None)
    args = parser.parse_args()

    driver = get_platform_driver(
        platform_name=args.platform,
        project_root=Path(args.project_root) if args.project_root else None,
        data_root=Path(args.data_root) if args.data_root else None,
    )
    result = driver.install_background_services()
    print(json.dumps({"platform": driver.platform_name(), **result}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
