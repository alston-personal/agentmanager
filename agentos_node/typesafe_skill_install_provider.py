"""Fixed Oracle TypeSafe skill installer for the bounded executor-job path."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
from typing import Any, Mapping

from agent_core.executor_job_contract import validate_executor_job
from agentos_node.executor_job_adapter import DEFAULT_PROVIDERS, ExecutorJobProviderRegistry

JOB_TYPE = "typesafe.skill.install"
PROVIDER_ID = "oracle-typesafe-skill-install-v1"
EXECUTOR_CLASS = "oracle-antigravity-skill-installer"
EXPECTED_HOME = Path("/home/ubuntu")
SKILL_FILE = EXPECTED_HOME / ".gemini/antigravity/skills/typesafe-ai/SKILL.md"
DATA_ROOT = EXPECTED_HOME / "agent-data"
RECEIPT_FILE = DATA_ROOT / "runtime/skills/typesafe-ai/install-receipt.json"
INSTALL_ARGV = (
    "npx", "--yes", "skills", "add", "typesafe-ai/skills",
    "--skill", "typesafe-ai", "--agent", "antigravity", "--global", "--yes",
)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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


def run_typesafe_skill_install(request: Mapping[str, Any]) -> dict[str, Any]:
    spec = validate_executor_job(request)
    if spec.job_type != JOB_TYPE or spec.executor_class != EXECUTOR_CLASS:
        return _failure("TYPESAFE_SKILL_PROVIDER_CONTRACT_MISMATCH", executor_available=False, routable=False, authorized=False)

    home = Path.home()
    if home != EXPECTED_HOME or os.environ.get("USER") not in (None, "", "ubuntu"):
        return _failure("TYPESAFE_SKILL_ORACLE_UBUNTU_IDENTITY_MISMATCH", executor_available=False, routable=False, authorized=False)
    if not DATA_ROOT.is_dir():
        return _failure("TYPESAFE_SKILL_AGENT_DATA_ROOT_UNAVAILABLE", executor_available=False, routable=False, authorized=False)

    npx = shutil.which("npx")
    if not npx:
        return _failure("TYPESAFE_SKILL_NPX_UNAVAILABLE", executor_available=False)

    argv = (npx, *INSTALL_ARGV[1:])
    try:
        proc = subprocess.run(
            argv,
            cwd=str(EXPECTED_HOME),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=300,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return _failure("TYPESAFE_SKILL_INSTALL_TIMEOUT")
    except OSError:
        return _failure("TYPESAFE_SKILL_INSTALL_LAUNCH_ERROR")

    if proc.returncode != 0:
        return _failure("TYPESAFE_SKILL_INSTALL_COMMAND_FAILED")
    if not SKILL_FILE.is_file() or SKILL_FILE.is_symlink():
        return _failure("TYPESAFE_SKILL_FILE_UNVERIFIED")
    text = SKILL_FILE.read_text(encoding="utf-8")
    if "name: typesafe-ai" not in text:
        return _failure("TYPESAFE_SKILL_IDENTITY_UNVERIFIED")

    digest = hashlib.sha256(SKILL_FILE.read_bytes()).hexdigest()
    receipt = {
        "schema": "agentos.skill-install-receipt/v1",
        "skill": "typesafe-ai",
        "agent": "antigravity",
        "scope": "oracle-ubuntu-global",
        "installation_method": "npx-skills-add",
        "installed_at": _now(),
        "skill_sha256": digest,
        "file_verified": True,
        "fresh_session_loaded": None,
        "agy_loaded": None,
        "credential_exposed": False,
    }
    RECEIPT_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = RECEIPT_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(RECEIPT_FILE)

    verify = json.loads(RECEIPT_FILE.read_text(encoding="utf-8"))
    receipt_ok = (
        verify.get("schema") == "agentos.skill-install-receipt/v1"
        and verify.get("skill") == "typesafe-ai"
        and verify.get("skill_sha256") == digest
        and verify.get("file_verified") is True
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


def register_typesafe_skill_install_provider(*, registry: ExecutorJobProviderRegistry = DEFAULT_PROVIDERS) -> bool:
    existing = registry.get(JOB_TYPE)
    if existing is not None:
        if existing.provider_id == PROVIDER_ID and existing.executor_class == EXECUTOR_CLASS:
            return True
        raise RuntimeError("typesafe skill provider already registered differently")
    registry.register(
        job_type=JOB_TYPE,
        provider_id=PROVIDER_ID,
        executor_class=EXECUTOR_CLASS,
        handler=run_typesafe_skill_install,
    )
    return True
