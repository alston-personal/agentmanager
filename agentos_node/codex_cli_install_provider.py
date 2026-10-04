"""Fixed Oracle Codex CLI installer for the bounded executor-job path."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
from typing import Any, Mapping

from agent_core.executor_job_contract import validate_executor_job
from agentos_node.executor_job_adapter import DEFAULT_PROVIDERS, ExecutorJobProviderRegistry

JOB_TYPE = "codex.cli.install"
PROVIDER_ID = "oracle-codex-cli-install-v1"
EXECUTOR_CLASS = "codex-cli"
EXPECTED_HOME = Path("/home/ubuntu")
DATA_ROOT = EXPECTED_HOME / "agent-data"
RECEIPT_FILE = DATA_ROOT / "runtime/codex-cli/install-receipt.json"


def _runtime_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _failure(classification: str, *, executor_available: bool = True, routable: bool = True, authorized: bool = True) -> dict[str, Any]:
    return {
        "verdict": "FAIL",
        "classification": classification,
        "install_receipt_ok": False,
        "executor_available": executor_available,
        "routable": routable,
        "authorized": authorized,
        "successful": False,
        "credential_exposed": False,
    }


def _classify_install_failure(returncode: int, combined: str) -> str:
    text = combined.casefold()
    if returncode == 2 or "run as oracle ubuntu user" in text:
        return "CODEX_CLI_ORACLE_UBUNTU_IDENTITY_MISMATCH"
    if returncode == 3 or "missing prerequisite" in text:
        return "CODEX_CLI_PREREQUISITE_MISSING"
    if returncode == 4 or "agentos data root missing" in text:
        return "CODEX_CLI_AGENT_DATA_ROOT_UNAVAILABLE"
    if any(token in text for token in ("permission denied", "eacces", "operation not permitted")):
        return "CODEX_CLI_INSTALL_PERMISSION_DENIED"
    if any(token in text for token in ("network is unreachable", "enotfound", "eai_again", "connection reset", "socket hang up", "etimedout")):
        return "CODEX_CLI_INSTALL_NETWORK"
    if any(token in text for token in ("e404", "404 not found", "package not found")):
        return "CODEX_CLI_PACKAGE_UNAVAILABLE"
    if "npm err!" in text or "npm error" in text:
        return "CODEX_CLI_INSTALL_NPM_FAILED"
    return "CODEX_CLI_INSTALL_COMMAND_FAILED"


def run_codex_cli_install(request: Mapping[str, Any], *, runtime_root: str | Path | None = None) -> dict[str, Any]:
    spec = validate_executor_job(request)
    if spec.job_type != JOB_TYPE or spec.executor_class != EXECUTOR_CLASS:
        return _failure("CODEX_CLI_PROVIDER_CONTRACT_MISMATCH", executor_available=False, routable=False, authorized=False)

    home = Path.home()
    if home != EXPECTED_HOME or os.environ.get("USER") not in (None, "", "ubuntu"):
        return _failure("CODEX_CLI_ORACLE_UBUNTU_IDENTITY_MISMATCH", executor_available=False, routable=False, authorized=False)
    if not DATA_ROOT.is_dir():
        return _failure("CODEX_CLI_AGENT_DATA_ROOT_UNAVAILABLE", executor_available=False, routable=False, authorized=False)

    root = Path(runtime_root) if runtime_root is not None else _runtime_root()
    installer = root / "scripts/install_oracle_codex_cli.sh"
    if not installer.is_file() or installer.is_symlink():
        return _failure("CODEX_CLI_INSTALLER_UNAVAILABLE", executor_available=False, routable=False, authorized=False)

    try:
        proc = subprocess.run(
            ["/bin/bash", str(installer)],
            cwd=str(root),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=600,
            check=False,
            env={
                "HOME": str(EXPECTED_HOME),
                "USER": "ubuntu",
                "PATH": f"{EXPECTED_HOME}/.local/bin:{EXPECTED_HOME}/.local/share/agentos/npm-global/bin:" + os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
                "AGENT_DATA_ROOT": str(DATA_ROOT),
            },
        )
    except subprocess.TimeoutExpired:
        return _failure("CODEX_CLI_INSTALL_TIMEOUT")
    except OSError:
        return _failure("CODEX_CLI_INSTALL_LAUNCH_ERROR")

    if proc.returncode != 0:
        return _failure(_classify_install_failure(proc.returncode, (proc.stdout or "") + "\n" + (proc.stderr or "")))
    if not RECEIPT_FILE.is_file() or RECEIPT_FILE.is_symlink():
        return _failure("CODEX_CLI_INSTALL_RECEIPT_MISSING")
    try:
        verify = json.loads(RECEIPT_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _failure("CODEX_CLI_INSTALL_RECEIPT_INVALID")

    receipt_ok = (
        verify.get("schema") == "agentos.codex-cli-install-receipt/v1"
        and verify.get("cli_installed") is True
        and verify.get("credential_exposed") is False
        and verify.get("auth_ready") is None
    )
    return {
        "verdict": "PASS" if receipt_ok else "FAIL",
        "classification": "CODEX_CLI_INSTALL_PASS" if receipt_ok else "CODEX_CLI_INSTALL_RECEIPT_INVALID",
        "install_receipt_ok": bool(receipt_ok),
        "executor_available": True,
        "routable": False,
        "authorized": False,
        "successful": bool(receipt_ok),
        "credential_exposed": False,
        "codex_cli_version": str(verify.get("codex_cli_version") or "")[:128],
    }


def register_codex_cli_install_provider(*, registry: ExecutorJobProviderRegistry = DEFAULT_PROVIDERS, runtime_root: str | Path | None = None) -> bool:
    root = Path(runtime_root) if runtime_root is not None else _runtime_root()
    installer = root / "scripts/install_oracle_codex_cli.sh"
    if not installer.is_file():
        return False
    existing = registry.get(JOB_TYPE)
    if existing is not None:
        if existing.provider_id == PROVIDER_ID and existing.executor_class == EXECUTOR_CLASS:
            return True
        raise RuntimeError("Codex CLI provider already registered differently")

    registry.register(
        job_type=JOB_TYPE,
        provider_id=PROVIDER_ID,
        executor_class=EXECUTOR_CLASS,
        handler=lambda request: run_codex_cli_install(request, runtime_root=root),
    )
    return True
