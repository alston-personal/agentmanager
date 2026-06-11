from __future__ import annotations

import os
import shutil
import subprocess
import shlex
from pathlib import Path
from typing import Any

from .base import BasePlatformDriver, ServiceSpec, utc_now, write_json
from .. import config


class LinuxPlatformDriver(BasePlatformDriver):
    def platform_name(self) -> str:
        return "linux"

    def volatile_state_dir(self) -> Path:
        shm = Path("/dev/shm/leopardcat-swarm")
        try:
            shm.mkdir(parents=True, exist_ok=True)
            return shm
        except Exception:
            return super().volatile_state_dir()

    def install_background_services(self) -> dict[str, Any]:
        script = self.project_root / "scripts" / "install_systemd_user.sh"
        if script.exists() and shutil.which("systemctl"):
            result = subprocess.run(
                ["bash", str(script)],
                cwd=str(self.project_root),
                env=self._build_env(),
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                fallback = super().install_background_services()
                fallback.update(
                    {
                        "installed": fallback.get("installed", 0),
                        "mode": "fallback-manifest",
                        "systemd_returncode": result.returncode,
                        "systemd_stderr": result.stderr.strip(),
                    }
                )
                return fallback
            payload = {
                "platform": self.platform_name(),
                "installed_at": utc_now(),
                "mode": "systemd",
                "script": str(script),
            }
            write_json(self._service_manifest_path(), payload)
            return {"installed": 1, "mode": "systemd", "script": str(script)}
        return super().install_background_services()

    def start_service(self, name: str) -> dict[str, Any]:
        if shutil.which("systemctl"):
            unit = name if name.endswith(".service") or name.endswith(".timer") else f"{name}.service"
            result = subprocess.run(
                ["systemctl", "--user", "start", unit],
                cwd=str(self.project_root),
                env=self._build_env(),
                capture_output=True,
                text=True,
            )
            payload = {
                "name": name,
                "unit": unit,
                "started_at": utc_now(),
                "returncode": result.returncode,
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
            }
            if result.returncode == 0:
                write_json(self._service_record_path(name), payload)
                return payload
            fallback = super().start_service(name)
            fallback.update({"mode": "fallback-subprocess", "systemd_returncode": result.returncode, "systemd_stderr": result.stderr.strip()})
            return fallback
        return super().start_service(name)

    def stop_service(self, name: str) -> dict[str, Any]:
        if shutil.which("systemctl"):
            unit = name if name.endswith(".service") or name.endswith(".timer") else f"{name}.service"
            result = subprocess.run(
                ["systemctl", "--user", "stop", unit],
                cwd=str(self.project_root),
                env=self._build_env(),
                capture_output=True,
                text=True,
            )
            payload = {
                "name": name,
                "unit": unit,
                "stopped_at": utc_now(),
                "returncode": result.returncode,
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
            }
            if result.returncode == 0:
                write_json(self._service_record_path(name), payload)
                return payload
            fallback = super().stop_service(name)
            fallback.update({"mode": "fallback-subprocess", "systemd_returncode": result.returncode, "systemd_stderr": result.stderr.strip()})
            return fallback
        return super().stop_service(name)

    def restart_service(self, name: str) -> dict[str, Any]:
        if shutil.which("systemctl"):
            unit = name if name.endswith(".service") or name.endswith(".timer") else f"{name}.service"
            result = subprocess.run(
                ["systemctl", "--user", "restart", unit],
                cwd=str(self.project_root),
                env=self._build_env(),
                capture_output=True,
                text=True,
            )
            payload = {
                "name": name,
                "unit": unit,
                "restarted_at": utc_now(),
                "returncode": result.returncode,
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
            }
            if result.returncode == 0:
                write_json(self._service_record_path(name), payload)
                return payload
            fallback = super().restart_service(name)
            fallback.update({"mode": "fallback-subprocess", "systemd_returncode": result.returncode, "systemd_stderr": result.stderr.strip()})
            return fallback
        return super().restart_service(name)

    def schedule_recurring_job(self, name: str, command: list[str] | str, interval_seconds: int) -> dict[str, Any]:
        if shutil.which("systemctl"):
            systemd_dir = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "systemd" / "user"
            systemd_dir.mkdir(parents=True, exist_ok=True)
            command_text = shlex.join(command) if isinstance(command, list) else str(command)
            service_unit = systemd_dir / f"{name}.service"
            timer_unit = systemd_dir / f"{name}.timer"
            service_unit.write_text(
                "\n".join(
                    [
                        "[Unit]",
                        f"Description=AgentOS recurring job: {name}",
                        "",
                        "[Service]",
                        "Type=oneshot",
                        f"WorkingDirectory={self.project_root}",
                        f"ExecStart=/bin/bash -lc {command_text!r}",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            timer_unit.write_text(
                "\n".join(
                    [
                        "[Unit]",
                        f"Description=AgentOS recurring job timer: {name}",
                        "",
                        "[Timer]",
                        f"OnBootSec={max(1, interval_seconds)}s",
                        f"OnUnitActiveSec={max(1, interval_seconds)}s",
                        f"Unit={name}.service",
                        "",
                        "[Install]",
                        "WantedBy=timers.target",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            subprocess.run(["systemctl", "--user", "daemon-reload"], check=False, env=self._build_env())
            enable_result = subprocess.run(["systemctl", "--user", "enable", "--now", f"{name}.timer"], check=False, env=self._build_env())
            payload = {
                "name": name,
                "command": command if isinstance(command, list) else [command],
                "interval_seconds": interval_seconds,
                "service_unit": str(service_unit),
                "timer_unit": str(timer_unit),
                "registered_at": utc_now(),
            }
            if enable_result.returncode == 0:
                write_json(self._scheduled_jobs_path(), {"jobs": [payload]})
                return payload
            fallback = super().schedule_recurring_job(name, command, interval_seconds)
            fallback.update({"mode": "fallback-manifest", "systemd_returncode": enable_result.returncode})
            return fallback
        return super().schedule_recurring_job(name, command, interval_seconds)
