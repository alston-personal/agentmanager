"""Read-only readiness probe for a persistent browser worker host.

This module deliberately does not automate any provider UI. It verifies only the
host boundary AgentOS needs before an external browser bridge is authorized:
Linux platform, browser/bridge executables, a persistent profile directory and a
usable display. Browser credentials remain outside AgentOS Core.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
import os
from pathlib import Path
import platform
import shutil
from typing import Mapping


@dataclass(frozen=True)
class BrowserWorkerProbeResult:
    platform: str
    browser_executable: str | None
    bridge_executable: str | None
    profile_dir: str
    profile_exists: bool
    profile_writable: bool
    display: str | None
    ready: bool
    issues: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def probe_browser_worker(
    *,
    profile_dir: str,
    browser_candidates: tuple[str, ...] = (
        "google-chrome",
        "google-chrome-stable",
        "chromium",
        "chromium-browser",
    ),
    bridge_executable: str = "bridge",
    environ: Mapping[str, str] | None = None,
) -> BrowserWorkerProbeResult:
    """Probe a browser-worker host without launching or modifying the browser."""

    env = os.environ if environ is None else environ
    system = platform.system().lower()
    issues: list[str] = []

    browser = next((shutil.which(name) for name in browser_candidates if shutil.which(name)), None)
    bridge = shutil.which(bridge_executable)
    profile = Path(profile_dir).expanduser()
    profile_exists = profile.exists()
    profile_writable = profile_exists and os.access(profile, os.W_OK)
    display = env.get("DISPLAY") or env.get("WAYLAND_DISPLAY")

    if system != "linux":
        issues.append("browser worker target is expected to be Linux")
    if browser is None:
        issues.append("Chrome/Chromium executable not found")
    if bridge is None:
        issues.append("browser bridge executable not found")
    if not profile_exists:
        issues.append("persistent browser profile directory does not exist")
    elif not profile_writable:
        issues.append("persistent browser profile directory is not writable")
    if not display:
        issues.append("no DISPLAY/WAYLAND_DISPLAY is available")

    return BrowserWorkerProbeResult(
        platform=system,
        browser_executable=browser,
        bridge_executable=bridge,
        profile_dir=str(profile),
        profile_exists=profile_exists,
        profile_writable=profile_writable,
        display=display,
        ready=not issues,
        issues=tuple(issues),
    )
