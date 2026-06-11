from __future__ import annotations

import contextlib
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import webbrowser
from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .. import config


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Unsupported JSON value: {type(value)!r}")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=_json_default), encoding="utf-8")
    tmp_path.replace(path)


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(payload, ensure_ascii=False, default=_json_default)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def tail_text(path: Path, max_chars: int = 6000) -> str:
    if not path.exists():
        return ""
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            if size <= max_chars:
                handle.seek(0)
            else:
                handle.seek(-max_chars, os.SEEK_END)
            raw = handle.read()
        return raw.decode("utf-8", errors="ignore")
    except Exception:
        try:
            content = path.read_text(encoding="utf-8")
            return content[-max_chars:]
        except Exception:
            return ""


@dataclass(slots=True)
class ServiceSpec:
    name: str
    command: list[str]
    cwd: str | None = None
    interval_seconds: int | None = None
    description: str = ""
    enabled: bool = True
    metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["command"] = list(self.command)
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ServiceSpec":
        return cls(
            name=str(payload.get("name") or ""),
            command=[str(part) for part in payload.get("command") or []],
            cwd=str(payload["cwd"]) if payload.get("cwd") else None,
            interval_seconds=int(payload["interval_seconds"]) if payload.get("interval_seconds") else None,
            description=str(payload.get("description") or ""),
            enabled=bool(payload.get("enabled", True)),
            metadata=payload.get("metadata") if isinstance(payload.get("metadata"), dict) else None,
        )


class PlatformLock:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._handle = None

    def acquire(self) -> "PlatformLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("a+")
        if os.name == "nt":
            import msvcrt

            try:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                handle.close()
                raise
        else:
            import fcntl

            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                handle.close()
                raise
        handle.seek(0)
        handle.truncate()
        handle.write(f"{os.getpid()}\n")
        handle.flush()
        self._handle = handle
        return self

    def release(self) -> None:
        if self._handle is None:
            return
        try:
            if os.name == "nt":
                import msvcrt

                try:
                    self._handle.seek(0)
                    msvcrt.locking(self._handle.fileno(), msvcrt.LK_UNLCK, 1)
                except OSError:
                    pass
            else:
                import fcntl

                try:
                    fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
                except OSError:
                    pass
        finally:
            self._handle.close()
            self._handle = None

    def __enter__(self) -> "PlatformLock":
        return self.acquire()

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()


class BasePlatformDriver(ABC):
    def __init__(self, project_root: Path | None = None, data_root: Path | None = None) -> None:
        self.project_root = Path(project_root or config.PROJECT_ROOT).expanduser().resolve()
        self.data_root = Path(data_root or config.AGENT_DATA_ROOT).expanduser().resolve()

    @abstractmethod
    def platform_name(self) -> str:
        raise NotImplementedError

    def runtime_dir(self) -> Path:
        return self.data_root / "runtime"

    def volatile_state_dir(self) -> Path:
        return self.runtime_dir() / "volatile"

    def persistent_state_dir(self) -> Path:
        return self.runtime_dir()

    def _logs_dir(self) -> Path:
        return self.data_root / "logs"

    def _service_manifest_path(self) -> Path:
        return self.persistent_state_dir() / "services" / "manifest.json"

    def _service_runtime_dir(self) -> Path:
        return self.persistent_state_dir() / "services" / "runtime"

    def _scheduled_jobs_path(self) -> Path:
        return self.persistent_state_dir() / "services" / "scheduled_jobs.json"

    def _job_runner_record_path(self, name: str) -> Path:
        return self._service_runtime_dir() / f"{name}.runner.json"

    def _service_record_path(self, name: str) -> Path:
        return self._service_runtime_dir() / f"{name}.json"

    def _service_log_path(self, name: str) -> Path:
        return self._logs_dir() / f"{name}.log"

    def _build_env(self) -> dict[str, str]:
        env = os.environ.copy()
        env.setdefault("AGENT_PROJECT_ROOT", str(self.project_root))
        env.setdefault("AGENT_DATA_ROOT", str(self.data_root))
        env.setdefault("AGENT_DATA_DIR", str(self.data_root))
        return env

    def default_service_specs(self) -> list[ServiceSpec]:
        python_bin = os.environ.get("PYTHON_BIN") or os.environ.get("PYTHON") or os.sys.executable or "python3"
        scripts_dir = self.project_root / "scripts"
        specs = [
            ServiceSpec(
                name="os-chronos",
                description="AgentOS Central Chronos Scheduler",
                command=[python_bin, str(scripts_dir / "chronos.py")],
                cwd=str(self.project_root),
            ),
            ServiceSpec(
                name="agent-maintenance",
                description="AgentOS Periodic Maintenance and Watchdog",
                command=[python_bin, str(scripts_dir / "maintenance.py")],
                cwd=str(self.project_root),
            ),
            ServiceSpec(
                name="tg-commander",
                description="AgentOS Telegram Command Bridge",
                command=[python_bin, str(scripts_dir / "tg_bridge.py")],
                cwd=str(self.project_root),
            ),
            ServiceSpec(
                name="cat-ink-syncer",
                description="AgentOS Cat-Ink Session Syncer",
                command=[python_bin, str(scripts_dir / "core_services" / "session_syncer.py")],
                cwd=str(self.project_root),
            ),
            ServiceSpec(
                name="os-lobster",
                description="AgentOS Lobster Autonomous Task Loop",
                command=[python_bin, str(scripts_dir / "lobster.py"), "--loop"],
                cwd=str(self.project_root),
            ),
        ]
        return specs

    def install_background_services(self) -> dict[str, Any]:
        specs = self.default_service_specs()
        manifest = {
            "platform": self.platform_name(),
            "generated_at": utc_now(),
            "project_root": str(self.project_root),
            "data_root": str(self.data_root),
            "services": [spec.to_dict() for spec in specs],
        }
        write_json(self._service_manifest_path(), manifest)
        return {"installed": len(specs), "manifest": str(self._service_manifest_path())}

    def _load_service_manifest(self) -> list[ServiceSpec]:
        payload = read_json(self._service_manifest_path(), default={}) or {}
        items = payload.get("services") if isinstance(payload, dict) else []
        if isinstance(items, list) and items:
            return [ServiceSpec.from_dict(item) for item in items if isinstance(item, dict) and item.get("name")]
        return self.default_service_specs()

    def _find_service_spec(self, name: str) -> ServiceSpec:
        for spec in self._load_service_manifest():
            if spec.name == name:
                return spec
        raise FileNotFoundError(f"Unknown service: {name}")

    def _current_service_pid(self, name: str) -> int | None:
        record = read_json(self._service_record_path(name), default={}) or {}
        pid = record.get("pid")
        return int(pid) if isinstance(pid, int) or (isinstance(pid, str) and pid.isdigit()) else None

    def _terminate_pid(self, pid: int) -> None:
        if pid <= 0:
            return
        try:
            os.kill(pid, signal.SIGTERM)
        except Exception:
            try:
                if os.name == "nt":
                    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], check=False, capture_output=True)
            except Exception:
                pass

    def start_service(self, name: str) -> dict[str, Any]:
        spec = self._find_service_spec(name)
        self._service_runtime_dir().mkdir(parents=True, exist_ok=True)
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
        record = {
            "name": spec.name,
            "pid": process.pid,
            "command": spec.command,
            "cwd": spec.cwd or str(self.project_root),
            "started_at": utc_now(),
            "log_file": str(log_path),
        }
        write_json(self._service_record_path(name), record)
        return record

    def stop_service(self, name: str) -> dict[str, Any]:
        record_path = self._service_record_path(name)
        record = read_json(record_path, default={}) or {}
        pid = self._current_service_pid(name)
        if pid:
            self._terminate_pid(pid)
        if record:
            record["stopped_at"] = utc_now()
            write_json(record_path, record)
        return record

    def restart_service(self, name: str) -> dict[str, Any]:
        self.stop_service(name)
        return self.start_service(name)

    def schedule_recurring_job(self, name: str, command: list[str] | str, interval_seconds: int) -> dict[str, Any]:
        self.persistent_state_dir().mkdir(parents=True, exist_ok=True)
        jobs = read_json(self._scheduled_jobs_path(), default={"jobs": []}) or {"jobs": []}
        if not isinstance(jobs, dict):
            jobs = {"jobs": []}
        entry = {
            "name": name,
            "command": command if isinstance(command, list) else [command],
            "interval_seconds": int(interval_seconds),
            "platform": self.platform_name(),
            "registered_at": utc_now(),
        }
        jobs["jobs"] = [job for job in jobs.get("jobs", []) if job.get("name") != name]
        jobs["jobs"].append(entry)
        write_json(self._scheduled_jobs_path(), jobs)
        runner = self._spawn_job_runner(name)
        entry["runner_pid"] = runner.get("pid")
        entry["runner_log"] = runner.get("log_file")
        write_json(self._scheduled_jobs_path(), jobs)
        write_json(self._job_runner_record_path(name), runner)
        return entry

    def _spawn_job_runner(self, name: str) -> dict[str, Any]:
        runner_script = self.project_root / "scripts" / "platform_job_runner.py"
        log_path = self._service_log_path(f"{name}.runner")
        log_path.parent.mkdir(parents=True, exist_ok=True)
        command = [
            sys.executable,
            str(runner_script),
            "--project-root",
            str(self.project_root),
            "--data-root",
            str(self.data_root),
            "--job-name",
            name,
        ]
        if not runner_script.exists():
            return {"name": name, "started_at": utc_now(), "mode": "missing-runner-script"}
        log_handle = log_path.open("a", encoding="utf-8")
        try:
            process = subprocess.Popen(
                command,
                cwd=str(self.project_root),
                env=self._build_env(),
                stdout=log_handle,
                stderr=subprocess.STDOUT,
            )
        finally:
            log_handle.close()
        return {
            "name": name,
            "pid": process.pid,
            "started_at": utc_now(),
            "command": command,
            "log_file": str(log_path),
            "mode": "polling-runner",
        }

    def _read_pulse_board(self) -> dict[str, Any]:
        volatile = self.volatile_state_dir() / "pulse.json"
        persistent = self.persistent_state_dir() / "pulse_snapshot.json"
        board = read_json(volatile, default={}) or {}
        if not board:
            board = read_json(persistent, default={}) or {}
        return board if isinstance(board, dict) else {}

    def _write_pulse_board(self, board: dict[str, Any]) -> None:
        self.volatile_state_dir().mkdir(parents=True, exist_ok=True)
        self.persistent_state_dir().mkdir(parents=True, exist_ok=True)
        write_json(self.volatile_state_dir() / "pulse.json", board)
        write_json(self.persistent_state_dir() / "pulse_snapshot.json", board)

    def write_pulse(self, agent: str, task: str, status: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        board = self._read_pulse_board()
        entry = {
            "agent": agent,
            "task": task,
            "status": status,
            "pid": os.getpid(),
            "timestamp": utc_now(),
            "metadata": metadata or {},
        }
        board[agent] = entry
        self._write_pulse_board(board)
        return entry

    def append_event(self, event_type: str, message: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        event = {
            "timestamp": utc_now(),
            "platform": self.platform_name(),
            "event_type": event_type,
            "message": message,
            "metadata": metadata or {},
        }
        volatile_log = self.volatile_state_dir() / "events.log"
        persistent_dir = self.persistent_state_dir() / "events_archive"
        self.volatile_state_dir().mkdir(parents=True, exist_ok=True)
        persistent_dir.mkdir(parents=True, exist_ok=True)
        append_jsonl(volatile_log, event)
        archive = persistent_dir / f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.jsonl"
        append_jsonl(archive, event)
        return event

    def restore_pulse_board(self) -> dict[str, Any]:
        board = self._read_pulse_board()
        restored = {}
        for agent, entry in board.items():
            if isinstance(entry, dict):
                updated = dict(entry)
                updated["status"] = "idle (restored)"
                restored[agent] = updated
        if restored:
            self._write_pulse_board(restored)
        return restored

    def sync_transcripts(self) -> dict[str, Any]:
        sources: list[Path] = []
        env_source = os.environ.get("AGENT_BRAIN_DIR")
        if env_source:
            sources.append(Path(env_source).expanduser())
        antigravity_dir = os.environ.get("ANTIGRAVITY_DIR")
        if antigravity_dir:
            sources.append(Path(antigravity_dir).expanduser() / "brain")
        sources.append(Path.home() / ".gemini" / "antigravity" / "brain")
        sources.append(self.data_root / "brain")

        destination = self.persistent_state_dir() / "transcripts"
        destination.mkdir(parents=True, exist_ok=True)

        copied = 0
        for source_root in sources:
            if not source_root.exists():
                continue
            for entry in source_root.rglob("*"):
                if not entry.is_file():
                    continue
                try:
                    relative = entry.relative_to(source_root)
                except ValueError:
                    relative = Path(entry.name)
                target = destination / source_root.name / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                if not target.exists() or entry.stat().st_mtime > target.stat().st_mtime:
                    shutil.copy2(entry, target)
                    copied += 1
        return {"copied": copied, "destination": str(destination)}

    def ensure_project_links(self, project_root: str | Path, data_root: str | Path) -> dict[str, Any]:
        project_root = Path(project_root).expanduser().resolve()
        data_root = Path(data_root).expanduser().resolve()
        project_name = project_root.name
        project_data_root = data_root / "projects" / project_name
        project_data_root.mkdir(parents=True, exist_ok=True)
        (project_data_root / "memory").mkdir(parents=True, exist_ok=True)

        status_src = project_data_root / "STATUS.md"
        memory_src = project_data_root / "memory"
        status_dst = project_root / "STATUS.md"
        memory_dst = project_root / "memory"

        self._ensure_link(status_src, status_dst, is_dir=False)
        self._ensure_link(memory_src, memory_dst, is_dir=True)
        return {
            "project": project_name,
            "status": str(status_dst),
            "memory": str(memory_dst),
        }

    def _ensure_link(self, source: Path, destination: Path, is_dir: bool) -> None:
        source.parent.mkdir(parents=True, exist_ok=True)
        if not source.exists() and is_dir:
            source.mkdir(parents=True, exist_ok=True)
        if destination.exists() or destination.is_symlink():
            if destination.is_symlink():
                try:
                    if destination.resolve() == source.resolve():
                        return
                except Exception:
                    pass
                destination.unlink()
            elif destination.is_dir():
                return
            else:
                destination.unlink()
        try:
            destination.symlink_to(source, target_is_directory=is_dir)
            return
        except Exception:
            pass
        if os.name == "nt" and is_dir:
            try:
                subprocess.run(["cmd", "/c", "mklink", "/J", str(destination), str(source)], check=True, capture_output=True)
                return
            except Exception:
                pass
        if is_dir:
            shutil.copytree(source, destination, dirs_exist_ok=True)
        else:
            if source.exists():
                shutil.copy2(source, destination)
            else:
                destination.touch()

    def acquire_lock(self, name: str) -> PlatformLock:
        lock_dir = self.persistent_state_dir() / "locks"
        return PlatformLock(lock_dir / f"{name}.lock")

    def open_in_browser(self, url: str) -> bool:
        return webbrowser.open(url)


def command_to_list(command: list[str] | tuple[str, ...] | str) -> list[str]:
    if isinstance(command, (list, tuple)):
        return [str(part) for part in command]
    return [str(command)]


def _service_name_to_unit(name: str, suffix: str) -> str:
    if name.endswith(suffix):
        return name
    return f"{name}{suffix}"


class GenericPlatformDriver(BasePlatformDriver):
    def platform_name(self) -> str:
        return "generic"
