"""Fixed #623 Antigravity CLI probe provider; no caller-controlled command."""
from __future__ import annotations

from pathlib import Path
import subprocess
import sys
from typing import Any, Mapping

from agent_core.executor_job_contract import validate_executor_job
from agentos_node.executor_job_adapter import DEFAULT_PROVIDERS, ExecutorJobProviderRegistry

JOB_TYPE = "antigravity.cli.probe"
PROVIDER_ID = "oracle-antigravity-cli-probe-v1"
EXECUTOR_CLASS = "antigravity-cli"


def run_antigravity_probe(request: Mapping[str, Any], *, runtime_root: Path | None = None) -> dict[str, Any]:
    spec = validate_executor_job(request)
    if spec.job_type != JOB_TYPE or spec.executor_class != EXECUTOR_CLASS:
        return {"classification": "CONTRACT_MISMATCH", "successful": False,
                "executor_available": False, "routable": False, "authorized": False, "verdict": "FAIL"}
    root = runtime_root or Path(__file__).resolve().parents[1]
    script = root / "scripts/probe_antigravity_cli_one.py"
    if not script.is_file() or script.is_symlink():
        return {"classification": "PROBE_NOT_DEPLOYED", "successful": False,
                "executor_available": False, "routable": False, "authorized": True, "verdict": "FAIL"}
    try:
        proc = subprocess.run([sys.executable, str(script)], cwd="/home/ubuntu",
                              stdin=subprocess.DEVNULL, capture_output=True, text=True,
                              check=False, timeout=105)
        # Script is trusted source, but output remains untrusted and sanitized.
        import json
        output = json.loads(proc.stdout)
        if not isinstance(output, dict) or output.get("schema") != "agentos.antigravity-cli-probe/v1":
            raise ValueError("invalid probe receipt")
        classification = str(output.get("classification", ""))[:80]
        successful = bool(proc.returncode == 0 and output.get("successful") is True
                          and classification == "ANTIGRAVITY_INFERENCE_PASS"
                          and output.get("expected_marker_matched") is True)
        version = str(output.get("version", ""))[:80]
        digest = str(output.get("sha256", ""))
        if not (len(digest) == 64 and all(c in "0123456789abcdef" for c in digest)):
            digest = ""
        return {
            "classification": classification if classification else "PROBE_INVALID_RECEIPT",
            "successful": successful,
            "executor_available": True,
            "routable": successful,
            "authorized": True,
            "verdict": "PASS" if successful else "FAIL",
            "gemini_cli_version": version,
            "agy_probe_sha256": digest,
            "agy_marker_matched": successful,
            "agy_version_exit_code": output.get("version_exit_code") if type(output.get("version_exit_code")) is int and -1 <= output["version_exit_code"] <= 255 else None,
            "agy_version_detected": output.get("version_detected") if type(output.get("version_detected")) is bool else None,
        }
    except (OSError, subprocess.TimeoutExpired, ValueError, TypeError):
        return {"classification": "PROBE_FAILED", "successful": False,
                "executor_available": True, "routable": False, "authorized": True, "verdict": "FAIL"}


def register_antigravity_probe_provider(*, registry: ExecutorJobProviderRegistry = DEFAULT_PROVIDERS,
                                        runtime_root: Path | None = None) -> bool:
    existing = registry.get(JOB_TYPE)
    if existing is not None:
        return existing.provider_id == PROVIDER_ID and existing.executor_class == EXECUTOR_CLASS
    registry.register(job_type=JOB_TYPE, provider_id=PROVIDER_ID,
                      executor_class=EXECUTOR_CLASS,
                      handler=lambda request: run_antigravity_probe(request, runtime_root=runtime_root))
    return True
