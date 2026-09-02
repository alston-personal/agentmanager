#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from agent_core.platform import get_platform_driver


def _native_install_failed(result: dict[str, object]) -> bool:
    """Return true only when a native service install was actually attempted and failed.

    Platforms without a native service manager may intentionally use the portable
    fallback manifest. A Linux host that *has* systemd and ran the systemd
    installer must not silently downgrade a failed mutation to a successful
    manifest-only receipt.
    """
    raw = result.get("systemd_returncode")
    return isinstance(raw, int) and not isinstance(raw, bool) and raw != 0


def _systemd_active(unit: str) -> bool:
    completed = subprocess.run(
        ["systemctl", "--user", "is-active", "--quiet", unit],
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.returncode == 0


def _verify_linux_core_services(result: dict[str, object]) -> str | None:
    """Verify the autonomous Core services that the successful systemd install promises.

    The control-plane deployment workflow validates its HTTP service separately.
    This verifier prevents a green service-install receipt while the newly
    installed persistent Supervisor or explicitly enabled shared Worker Host has
    already failed to stay active.
    """
    if result.get("mode") != "systemd":
        return None
    if str(os.environ.get("AGENT_MODE") or "CLIENT").strip().upper() != "CORE":
        return None
    if not _systemd_active("agentos-core-supervisor.service"):
        return "core_supervisor_service_not_active"
    if str(os.environ.get("AGENTOS_CORE_EMPLOYEE_WORKER_HOST_ENABLE") or "0").strip() == "1":
        if not _systemd_active("agentos-employee-worker-host.service"):
            return "employee_worker_host_service_not_active"
    return None


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

    if driver.platform_name() == "linux":
        verification_error = _verify_linux_core_services(result)
        if verification_error:
            payload["ok"] = False
            payload["error_code"] = verification_error
            print(json.dumps(payload, indent=2, ensure_ascii=False))
            return 2

    payload["ok"] = True
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
