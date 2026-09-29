"""Fixed Oracle TypeSafe skill installer for the bounded executor-job path."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
from typing import Any, Mapping

from agent_core.executor_job_contract import validate_executor_job
from agentos_node.executor_job_adapter import DEFAULT_PROVIDERS, ExecutorJobProviderRegistry

JOB_TYPE = "typesafe.skill.install"
PROVIDER_ID = "oracle-typesafe-skill-install-v1"
EXECUTOR_CLASS = "oracle-antigravity-skill-installer"
EXPECTED_HOME = Path("/home/ubuntu")
DATA_ROOT = EXPECTED_HOME / "agent-data"
RECEIPT_FILE = DATA_ROOT / "runtime/skills/typesafe-ai/install-receipt.json"


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


def run_typesafe_skill_install(request: Mapping[str, Any], *, runtime_root: str | Path | None = None) -> dict[str, Any]:
    spec = validate_executor_job(request)
    if spec.job_type != JOB_TYPE or spec.executor_class != EXECUTOR_CLASS:
        return _failure("TYPESAFE_SKILL_PROVIDER_CONTRACT_MISMATCH", executor_available=False, routable=False, authorized=False)

    home = Path.home()
    if home != EXPECTED_HOME or os.environ.get("USER") not in (None, "", "ubuntu"):
        return _failure("TYPESAFE_SKILL_ORACLE_UBUNTU_IDENTITY_MISMATCH", executor_available=False, routable=False, authorized=False)
    if not DATA_ROOT.is_dir():
        return _failure("TYPESAFE_SKILL_AGENT_DATA_ROOT_UNAVAILABLE", executor_available=False, routable=False, authorized=False)

    root = Path(runtime_root) if runtime_root is not None else _runtime_root()
    installer = root / "scripts/install_oracle_typesafe_skill.sh"
    if not installer.is_file() or installer.is_symlink():
        return _failure("TYPESAFE_SKILL_INSTALLER_UNAVAILABLE", executor_available=False, routable=False, authorized=False)

    try:
        proc = subprocess.run(
            ["/bin/bash", str(installer)],
            cwd=str(root),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=300,
            check=False,
            env={
                "HOME": str(EXPECTED_HOME),
                "USER": "ubuntu",
                "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
                "AGENT_DATA_ROOT": str(DATA_ROOT),
            },
        )
    except subprocess.TimeoutExpired:
        return _failure("TYPESAFE_SKILL_INSTALL_TIMEOUT")
    except OSError:
        return _failure("TYPESAFE_SKILL_INSTALL_LAUNCH_ERROR")

    if proc.returncode != 0:
        return _failure("TYPESAFE_SKILL_INSTALL_COMMAND_FAILED")
    if not RECEIPT_FILE.is_file() or RECEIPT_FILE.is_symlink():
        return _failure("TYPESAFE_SKILL_INSTALL_RECEIPT_MISSING")

    try:
        verify = json.loads(RECEIPT_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _failure("TYPESAFE_SKILL_INSTALL_RECEIPT_INVALID")

    receipt_ok = (
        verify.get("schema") == "agentos.skill-install-receipt/v1"
        and verify.get("skill") == "typesafe-ai"
        and isinstance(verify.get("skill_sha256"), str)
        and len(verify.get("skill_sha256")) == 64
        and verify.get("file_verified") is True
        and verify.get("fresh_session_loaded") is None
        and verify.get("agy_loaded") is None
        and verify.get("credential_exposed") is False
    )
    return {
        "verdict": "PASS" if receipt_ok else "FAIL",
        "classification": "TYPESAFE_SKILL_INSTALL_PASS" if receipt_ok else "TYPESAFE_SKILL_INSTALL_RECEIPT_INVALID",
        "install_receipt_ok": bool(receipt_ok),
        "executor_available": True,
        "routable": True,
        "authorized": True,
        "successful": bool(receipt_ok),
        "credential_exposed": False,
    }


def register_typesafe_skill_install_provider(*, registry: ExecutorJobProviderRegistry = DEFAULT_PROVIDERS, runtime_root: str | Path | None = None) -> bool:
    root = Path(runtime_root) if runtime_root is not None else _runtime_root()
    installer = root / "scripts/install_oracle_typesafe_skill.sh"
    if not installer.is_file():
        return False
    existing = registry.get(JOB_TYPE)
    if existing is not None:
        if existing.provider_id == PROVIDER_ID and existing.executor_class == EXECUTOR_CLASS:
            return True
        raise RuntimeError("typesafe skill provider already registered differently")

    def handler(request: Mapping[str, Any]) -> Mapping[str, Any]:
        return run_typesafe_skill_install(request, runtime_root=root)

    registry.register(
        job_type=JOB_TYPE,
        provider_id=PROVIDER_ID,
        executor_class=EXECUTOR_CLASS,
        handler=handler,
    )
    return True
