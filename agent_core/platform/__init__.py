from __future__ import annotations

import os
import platform as py_platform
from pathlib import Path

from .base import BasePlatformDriver, GenericPlatformDriver
from .linux import LinuxPlatformDriver
from .macos import MacOSPlatformDriver
from .windows import WindowsPlatformDriver


def normalize_platform_name(name: str | None = None) -> str:
    candidate = (name or os.environ.get("AGENT_PLATFORM") or py_platform.system() or "linux").strip().lower()
    mapping = {
        "linux": "linux",
        "linux2": "linux",
        "windows": "windows",
        "win32": "windows",
        "cygwin": "windows",
        "darwin": "macos",
        "mac": "macos",
        "macos": "macos",
        "osx": "macos",
    }
    return mapping.get(candidate, candidate)


def get_platform_driver(
    platform_name: str | None = None,
    project_root: str | Path | None = None,
    data_root: str | Path | None = None,
) -> BasePlatformDriver:
    normalized = normalize_platform_name(platform_name)
    if normalized == "linux":
        return LinuxPlatformDriver(project_root=Path(project_root) if project_root else None, data_root=Path(data_root) if data_root else None)
    if normalized == "windows":
        return WindowsPlatformDriver(project_root=Path(project_root) if project_root else None, data_root=Path(data_root) if data_root else None)
    if normalized == "macos":
        return MacOSPlatformDriver(project_root=Path(project_root) if project_root else None, data_root=Path(data_root) if data_root else None)
    return GenericPlatformDriver(project_root=Path(project_root) if project_root else None, data_root=Path(data_root) if data_root else None)


def platform_name(platform_override: str | None = None) -> str:
    return get_platform_driver(platform_override).platform_name()
