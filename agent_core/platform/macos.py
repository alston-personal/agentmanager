from __future__ import annotations

import subprocess
from pathlib import Path

from .windows import WindowsPlatformDriver


class MacOSPlatformDriver(WindowsPlatformDriver):
    def platform_name(self) -> str:
        return "macos"

    def runtime_dir(self) -> Path:
        support = Path.home() / "Library" / "Application Support" / "AgentOS" / "runtime"
        support.mkdir(parents=True, exist_ok=True)
        return support

    def volatile_state_dir(self) -> Path:
        cache = Path.home() / "Library" / "Caches" / "AgentOS" / "volatile"
        cache.mkdir(parents=True, exist_ok=True)
        return cache

    def open_in_browser(self, url: str) -> bool:
        try:
            return subprocess.run(["open", url], check=False).returncode == 0
        except Exception:
            return super().open_in_browser(url)
