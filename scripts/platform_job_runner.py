#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent_core.platform import get_platform_driver


def _load_jobs(driver, registry_path: Path) -> list[dict]:
    if not registry_path.exists():
        return []
    try:
        payload = json.loads(registry_path.read_text(encoding="utf-8"))
    except Exception:
        return []
    jobs = payload.get("jobs") if isinstance(payload, dict) else []
    return [job for job in jobs if isinstance(job, dict)]


def _run_command(command: list[str], cwd: str | None, env: dict[str, str], log_path: Path) -> int:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as log_handle:
        proc = subprocess.Popen(
            command,
            cwd=cwd,
            env=env,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
        )
        return proc.wait()


def main() -> int:
    parser = argparse.ArgumentParser(description="AgentOS recurring job runner")
    parser.add_argument("--platform", default=None)
    parser.add_argument("--project-root", default=None)
    parser.add_argument("--data-root", default=None)
    parser.add_argument("--job-name", required=True)
    args = parser.parse_args()

    driver = get_platform_driver(
        platform_name=args.platform,
        project_root=Path(args.project_root) if args.project_root else None,
        data_root=Path(args.data_root) if args.data_root else None,
    )
    registry_path = driver.persistent_state_dir() / "services" / "scheduled_jobs.json"
    lock = driver.acquire_lock(f"job_runner_{args.job_name}")
    lock.acquire()
    try:
        last_run = 0.0
        while True:
            jobs = _load_jobs(driver, registry_path)
            job = next((item for item in jobs if item.get("name") == args.job_name), None)
            if not job:
                time.sleep(5)
                continue

            interval = max(1, int(job.get("interval_seconds") or 60))
            command = job.get("command") or []
            if isinstance(command, str):
                command = [command]
            cwd = job.get("cwd") or str(driver.project_root)
            if time.time() - last_run >= interval:
                last_run = time.time()
                env = driver._build_env()  # type: ignore[attr-defined]
                env["AGENT_PLATFORM"] = driver.platform_name()
                env["AGENT_JOB_NAME"] = args.job_name
                driver.append_event(
                    "job_runner_tick",
                    f"Executing recurring job {args.job_name}",
                    metadata={"command": command, "interval_seconds": interval},
                )
                _run_command([str(part) for part in command], cwd, env, driver._logs_dir() / f"{args.job_name}.log")  # type: ignore[attr-defined]
            time.sleep(2)
    finally:
        lock.release()


if __name__ == "__main__":
    raise SystemExit(main())
