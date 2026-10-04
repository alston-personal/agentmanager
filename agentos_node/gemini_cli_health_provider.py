"""Bounded read-only Gemini CLI health provider for Oracle."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
from typing import Any, Mapping

from agent_core.executor_job_contract import validate_executor_job
from agentos_node.executor_job_adapter import DEFAULT_PROVIDERS, ExecutorJobProviderRegistry

JOB_TYPE = "gemini.cli.health"
PROVIDER_ID = "oracle-gemini-cli-health-v1"
EXECUTOR_CLASS = "gemini-cli"
EXPECTED_HOME = Path("/home/ubuntu")
GEMINI_BIN = EXPECTED_HOME / ".local/bin/gemini"


def _failure(classification: str, *, available: bool = True) -> dict[str, Any]:
    return {
        "verdict": "FAIL",
        "classification": classification,
        "executor_available": available,
        "routable": False,
        "authorized": False,
        "successful": False,
        "credential_exposed": False,
        "executor_provider": "gemini",
        "executor_timed_out": classification == "GEMINI_CLI_HEALTH_TIMEOUT",
    }


def _classify(returncode: int | None, combined: str, *, timed_out: bool = False) -> str:
    text = str(combined or "").casefold()
    if timed_out:
        return "GEMINI_CLI_HEALTH_TIMEOUT"
    if any(token in text for token in ("login", "sign in", "not authenticated", "unauthorized", "authentication required")):
        return "GEMINI_CLI_AUTH_REQUIRED"
    if any(token in text for token in ("rate limit", "too many requests", "quota", "resource exhausted")):
        return "GEMINI_CLI_RATE_LIMITED"
    if any(token in text for token in ("enotfound", "eai_again", "network is unreachable", "connection reset", "etimedout")):
        return "GEMINI_CLI_NETWORK"
    if returncode == 0 and "ready" in text:
        return "GEMINI_CLI_HEALTH_READY"
    return "GEMINI_CLI_HEALTH_NONZERO"


def run_gemini_cli_health(request: Mapping[str, Any]) -> dict[str, Any]:
    spec = validate_executor_job(request)
    if spec.job_type != JOB_TYPE or spec.executor_class != EXECUTOR_CLASS:
        return _failure("GEMINI_CLI_HEALTH_CONTRACT_MISMATCH", available=False)
    if Path.home() != EXPECTED_HOME or os.environ.get("USER") not in (None, "", "ubuntu"):
        return _failure("GEMINI_CLI_ORACLE_UBUNTU_IDENTITY_MISMATCH", available=False)
    if not GEMINI_BIN.is_file() or not os.access(GEMINI_BIN, os.X_OK):
        return _failure("GEMINI_CLI_INSTALL_REQUIRED", available=False)

    argv = [
        str(GEMINI_BIN),
        "-p", "AgentOS provider health probe. Do not modify files. Reply exactly READY.",
        "--approval-mode", "plan",
        "--output-format", "json",
        "--skip-trust",
    ]
    try:
        proc = subprocess.run(
            argv,
            cwd="/home/ubuntu/agentmanager",
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=60,
            check=False,
            env={**os.environ, "HOME": str(EXPECTED_HOME), "USER": "ubuntu", "CI": "1"},
        )
    except subprocess.TimeoutExpired as exc:
        combined=((exc.stdout or "") if isinstance(exc.stdout,str) else "")+"\n"+((exc.stderr or "") if isinstance(exc.stderr,str) else "")
        return _failure(_classify(None, combined, timed_out=True))
    except OSError:
        return _failure("GEMINI_CLI_HEALTH_LAUNCH_ERROR")

    combined=(proc.stdout or "")+"\n"+(proc.stderr or "")
    classification=_classify(proc.returncode, combined)
    if classification != "GEMINI_CLI_HEALTH_READY":
        result=_failure(classification)
        result["executor_returncode"]=int(proc.returncode)
        return result
    return {
        "verdict": "PASS",
        "classification": classification,
        "executor_available": True,
        "routable": True,
        "authorized": True,
        "successful": True,
        "credential_exposed": False,
        "executor_provider": "gemini",
        "executor_returncode": int(proc.returncode),
        "executor_timed_out": False,
    }


def register_gemini_cli_health_provider(*, registry: ExecutorJobProviderRegistry = DEFAULT_PROVIDERS) -> bool:
    existing=registry.get(JOB_TYPE)
    if existing is not None:
        if existing.provider_id == PROVIDER_ID and existing.executor_class == EXECUTOR_CLASS:
            return True
        raise RuntimeError("Gemini CLI health provider already registered differently")
    registry.register(
        job_type=JOB_TYPE,
        provider_id=PROVIDER_ID,
        executor_class=EXECUTOR_CLASS,
        handler=run_gemini_cli_health,
    )
    return True
