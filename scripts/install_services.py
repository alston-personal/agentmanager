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


def _native_install_failed(result: dict[str, object]) -> bool:
    """Return true only when a native service install was actually attempted and failed.

    Platforms without a native service manager may intentionally use the portable
    fallback manifest.  A Linux host that *has* systemd and ran the systemd
    installer must not silently downgrade a failed mutation to a successful
    manifest-only receipt.
    """
    raw = result.get("systemd_returncode")
    return isinstance(raw, int) and not isinstance(raw, bool) and raw != 0


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
    payload = {"platform": driver.platform_name(), **result}
    if _native_install_failed(result):
        payload["ok"] = False
        payload["error_code"] = "native_background_service_install_failed"
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 2
    payload["ok"] = True
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
