"""Fixed Oracle Gemini CLI + ONE installer for the bounded executor-job path."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
from typing import Any, Mapping

from agent_core.executor_job_contract import validate_executor_job
from agentos_node.executor_job_adapter import DEFAULT_PROVIDERS, ExecutorJobProviderRegistry

JOB_TYPE = "gemini.cli.install"
PROVIDER_ID = "oracle-gemini-cli-one-install-v1"
EXECUTOR_CLASS = "gemini-cli"
EXPECTED_HOME = Path("/home/ubuntu")
DATA_ROOT = EXPECTED_HOME / "agent-data"
RECEIPT_FILE = DATA_ROOT / "runtime/gemini-cli-one/install-receipt.json"


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



def _install_failure_classification(stdout: str, stderr: str) -> str:
    text = (str(stdout or "") + "\n" + str(stderr or "")).casefold()
    if any(token in text for token in ("eacces", "permission denied", "operation not permitted")):
        return "GEMINI_CLI_INSTALL_PERMISSION_DENIED"
    if any(token in text for token in ("ebadengine", "unsupported engine", "required: { node", "not compatible with your version of node")):
        return "GEMINI_CLI_NODE_INCOMPATIBLE"
    if any(token in text for token in ("enotfound", "eai_again", "network is unreachable", "connection reset", "socket hang up", "etimedout")):
        return "GEMINI_CLI_INSTALL_NETWORK"
    if any(token in text for token in ("e404", "404 not found", "package not found")):
        return "GEMINI_CLI_PACKAGE_UNAVAILABLE"
    return "GEMINI_CLI_INSTALL_COMMAND_FAILED"

def run_gemini_cli_install(request: Mapping[str, Any], *, runtime_root: str | Path | None = None) -> dict[str, Any]:
    spec = validate_executor_job(request)
    if spec.job_type != JOB_TYPE or spec.executor_class != EXECUTOR_CLASS:
        return _failure("GEMINI_CLI_PROVIDER_CONTRACT_MISMATCH", executor_available=False, routable=False, authorized=False)

    home = Path.home()
    if home != EXPECTED_HOME or os.environ.get("USER") not in (None, "", "ubuntu"):
        return _failure("GEMINI_CLI_ORACLE_UBUNTU_IDENTITY_MISMATCH", executor_available=False, routable=False, authorized=False)
    if not DATA_ROOT.is_dir():
        return _failure("GEMINI_CLI_AGENT_DATA_ROOT_UNAVAILABLE", executor_available=False, routable=False, authorized=False)

    root = Path(runtime_root) if runtime_root is not None else _runtime_root()
    installer = root / "scripts/install_oracle_gemini_cli_one.sh"
    if not installer.is_file() or installer.is_symlink():
        return _failure("GEMINI_CLI_INSTALLER_UNAVAILABLE", executor_available=False, routable=False, authorized=False)

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
                "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
                "AGENT_DATA_ROOT": str(DATA_ROOT),
            },
        )
    except subprocess.TimeoutExpired:
        return _failure("GEMINI_CLI_INSTALL_TIMEOUT")
    except OSError:
        return _failure("GEMINI_CLI_INSTALL_LAUNCH_ERROR")

    if proc.returncode != 0:
        return _failure(_install_failure_classification(proc.stdout, proc.stderr))
    if not RECEIPT_FILE.is_file() or RECEIPT_FILE.is_symlink():
        return _failure("GEMINI_CLI_INSTALL_RECEIPT_MISSING")
    try:
        verify = json.loads(RECEIPT_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _failure("GEMINI_CLI_INSTALL_RECEIPT_INVALID")

    receipt_ok = (
        verify.get("schema") == "agentos.gemini-cli-one-install-receipt/v1"
        and verify.get("cli_installed") is True
        and verify.get("one_mcp_configured") is True
        and verify.get("session_start_hook_configured") is True
        and verify.get("credential_exposed") is False
        and verify.get("auth_ready") is None
        and verify.get("live_sessionstart_verified") is None
    )
    return {
        "verdict": "PASS" if receipt_ok else "FAIL",
        "classification": "GEMINI_CLI_ONE_INSTALL_PASS" if receipt_ok else "GEMINI_CLI_INSTALL_RECEIPT_INVALID",
        "install_receipt_ok": bool(receipt_ok),
        "executor_available": True,
        "routable": True,
        "authorized": True,
        "successful": bool(receipt_ok),
        "credential_exposed": False,
    }


def register_gemini_cli_install_provider(*, registry: ExecutorJobProviderRegistry = DEFAULT_PROVIDERS, runtime_root: str | Path | None = None) -> bool:
    root = Path(runtime_root) if runtime_root is not None else _runtime_root()
    installer = root / "scripts/install_oracle_gemini_cli_one.sh"
    if not installer.is_file():
        return False
    existing = registry.get(JOB_TYPE)
    if existing is not None:
        if existing.provider_id == PROVIDER_ID and existing.executor_class == EXECUTOR_CLASS:
            return True
        raise RuntimeError("Gemini CLI provider already registered differently")

    def handler(request: Mapping[str, Any]) -> Mapping[str, Any]:
        return run_gemini_cli_install(request, runtime_root=root)

    registry.register(
        job_type=JOB_TYPE,
        provider_id=PROVIDER_ID,
        executor_class=EXECUTOR_CLASS,
        handler=handler,
    )
    return True
