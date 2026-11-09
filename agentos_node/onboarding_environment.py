from __future__ import annotations

import os
import platform
import shutil
from pathlib import Path
from typing import Any


def detect_package_manager() -> str | None:
    for name in ("apt-get", "dnf", "yum", "pacman", "zypper", "brew"):
        if shutil.which(name):
            return name
    return None


def detect_service_manager() -> str:
    system = platform.system()
    if system == "Windows":
        return "scheduled-task"
    if system == "Darwin":
        return "launchd"
    if system == "Linux":
        if shutil.which("systemctl"):
            return "systemd-user"
        return "unknown"
    return "unknown"


def detect_environment() -> dict[str, Any]:
    system = platform.system()
    home = str(Path.home())
    return {
        "schema": "agentos.onboarding-environment/v0.1",
        "os": system,
        "platform_release": platform.release(),
        "architecture": platform.machine(),
        "python": shutil.which("python3") or shutil.which("python"),
        "git": shutil.which("git"),
        "curl": shutil.which("curl"),
        "package_manager": detect_package_manager(),
        "service_manager": detect_service_manager(),
        "home": home,
        "user": os.environ.get("USER") or os.environ.get("USERNAME"),
        "is_wsl": system == "Linux" and "microsoft" in platform.release().lower(),
    }


def onboarding_requirements(env: dict[str, Any]) -> dict[str, Any]:
    os_name = str(env.get("os") or "")
    service = str(env.get("service_manager") or "")
    blockers: list[str] = []

    if not env.get("python"):
        blockers.append("python_missing")
    if not env.get("git"):
        blockers.append("git_missing")

    if os_name == "Linux" and service != "systemd-user":
        blockers.append("linux_systemd_user_unavailable")
    elif os_name == "Darwin" and service != "launchd":
        blockers.append("macos_launchd_unavailable")
    elif os_name == "Windows" and service != "scheduled-task":
        blockers.append("windows_task_scheduler_unavailable")
    elif os_name not in {"Linux", "Darwin", "Windows"}:
        blockers.append("unsupported_os")

    return {
        "schema": "agentos.onboarding-requirements/v0.1",
        "supported": not blockers,
        "blockers": blockers,
        "strategy": {
            "runtime": "python",
            "supervisor": service,
            "package_manager": env.get("package_manager"),
        },
    }
