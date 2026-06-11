from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from .base import BasePlatformDriver, utc_now, write_json


class WindowsPlatformDriver(BasePlatformDriver):
    def platform_name(self) -> str:
        return "windows"

    def runtime_dir(self) -> Path:
        local_appdata = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        if local_appdata:
            return Path(local_appdata).expanduser() / "AgentOS" / "runtime"
        return super().runtime_dir()

    def volatile_state_dir(self) -> Path:
        return self.runtime_dir() / "volatile"

    def persistent_state_dir(self) -> Path:
        return self.runtime_dir()

    def install_background_services(self) -> dict[str, Any]:
        manifest = super().install_background_services()
        manifest["mode"] = "local-process-registry"
        return manifest

    def start_service(self, name: str) -> dict[str, Any]:
        spec = self._find_service_spec(name)
        log_path = self._service_log_path(name)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_handle = log_path.open("a", encoding="utf-8")
        try:
            process = subprocess.Popen(
                spec.command,
                cwd=spec.cwd or str(self.project_root),
                env=self._build_env(),
                stdout=log_handle,
                stderr=subprocess.STDOUT,
            )
        finally:
            log_handle.close()
        payload = {
            "name": spec.name,
            "pid": process.pid,
            "command": spec.command,
            "cwd": spec.cwd or str(self.project_root),
            "started_at": utc_now(),
            "log_file": str(log_path),
            "platform": self.platform_name(),
        }
        write_json(self._service_record_path(name), payload)
        return payload

    def stop_service(self, name: str) -> dict[str, Any]:
        record = super().stop_service(name)
        record["platform"] = self.platform_name()
        return record

    def restart_service(self, name: str) -> dict[str, Any]:
        self.stop_service(name)
        return self.start_service(name)

    def schedule_recurring_job(self, name: str, command: list[str] | str, interval_seconds: int) -> dict[str, Any]:
        payload = {
            "name": name,
            "command": command if isinstance(command, list) else [command],
            "interval_seconds": int(interval_seconds),
            "platform": self.platform_name(),
            "registered_at": utc_now(),
            "mode": "polling-registry",
        }
        jobs = {"jobs": []}
        if self._scheduled_jobs_path().exists():
            try:
                jobs = json.loads(self._scheduled_jobs_path().read_text(encoding="utf-8"))
            except Exception:
                jobs = {"jobs": []}
        jobs["jobs"] = [job for job in jobs.get("jobs", []) if job.get("name") != name]
        jobs["jobs"].append(payload)
        write_json(self._scheduled_jobs_path(), jobs)
        runner = self._spawn_job_runner(name)
        payload["runner_pid"] = runner.get("pid")
        payload["runner_log"] = runner.get("log_file")
        write_json(self._job_runner_record_path(name), runner)
        return payload

    def open_in_browser(self, url: str) -> bool:
        try:
            return subprocess.run(["cmd", "/c", "start", "", url], check=False).returncode == 0
        except Exception:
            return super().open_in_browser(url)
