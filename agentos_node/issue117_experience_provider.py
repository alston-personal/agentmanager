"""Trusted provider bridge from the generic executor-job contract to issue #117.

#117 owns Experience discovery/hydration/regression semantics. This module does
not copy or reimplement that benchmark. It registers only when the same
immutable runtime generation already contains #117's regression entrypoint.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any, Mapping

from agent_core.executor_job_contract import validate_executor_job
from agentos_node.executor_job_adapter import DEFAULT_PROVIDERS, ExecutorJobProviderRegistry

JOB_TYPE = "experience.regression"
PROVIDER_ID = "issue117-experience-regression-v2"
EXECUTOR_CLASS = "openai-codex-local"
_ENTRY_REL = Path("scripts/oracle_codex_experience_regression_entry_v2.py")
_BASE_REL = Path("scripts/oracle_codex_experience_regression.py")
_PROVIDER_TIMEOUT_SECONDS = 420
_INNER_TIMEOUT_SECONDS = 180


def _runtime_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _provider_files(root: Path) -> tuple[Path, Path]:
    return root / _ENTRY_REL, root / _BASE_REL


def provider_implementation_available(root: str | Path | None = None) -> bool:
    runtime = Path(root) if root is not None else _runtime_root()
    entry, base = _provider_files(runtime)
    return entry.is_file() and base.is_file()


def _load_regression_module(path: Path):
    spec = importlib.util.spec_from_file_location("_agentos_issue117_regression", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("issue117 regression module load failed")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _score(payload: Mapping[str, Any], lane: str) -> float | None:
    branch = payload.get(lane)
    if not isinstance(branch, Mapping):
        return None
    score = branch.get("score")
    if not isinstance(score, Mapping):
        return None
    value = score.get("score")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def _bounded_failure(classification: str, *, executor_available: bool, routable: bool = True, authorized: bool = True) -> dict[str, Any]:
    return {
        "verdict": "FAIL",
        "classification": classification,
        "executor_available": executor_available,
        "routable": routable,
        "authorized": authorized,
        "successful": False,
        "credential_exposed": False,
    }


def run_issue117_experience_regression(request: Mapping[str, Any], *, runtime_root: str | Path | None = None) -> dict[str, Any]:
    spec = validate_executor_job(request)
    if spec.job_type != JOB_TYPE or spec.executor_class != EXECUTOR_CLASS:
        return _bounded_failure("EXPERIENCE_PROVIDER_CONTRACT_MISMATCH", executor_available=False, routable=False, authorized=False)
    root = Path(runtime_root) if runtime_root is not None else _runtime_root()
    entry, base = _provider_files(root)
    if not entry.is_file() or not base.is_file():
        return _bounded_failure("EXPERIENCE_PROVIDER_IMPLEMENTATION_UNAVAILABLE", executor_available=False, routable=False, authorized=False)
    try:
        regression = _load_regression_module(base)
        regression.find_codex()
    except FileNotFoundError:
        return _bounded_failure("EXPERIENCE_CODEX_EXECUTOR_UNAVAILABLE", executor_available=False)
    except Exception:
        return _bounded_failure("EXPERIENCE_CODEX_DISCOVERY_ERROR", executor_available=False)
    with tempfile.TemporaryDirectory(prefix="agentos-issue117-provider-") as tmp:
        output = Path(tmp) / "regression.json"
        argv = [sys.executable, str(entry), "--output", str(output), "--timeout", str(_INNER_TIMEOUT_SECONDS)]
        try:
            proc = subprocess.run(argv, cwd=root, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=_PROVIDER_TIMEOUT_SECONDS, check=False)
        except subprocess.TimeoutExpired:
            return _bounded_failure("EXPERIENCE_REGRESSION_PROVIDER_TIMEOUT", executor_available=True)
        except Exception:
            return _bounded_failure("EXPERIENCE_REGRESSION_PROVIDER_ERROR", executor_available=True)
        if not output.is_file():
            return _bounded_failure("EXPERIENCE_REGRESSION_EVIDENCE_MISSING", executor_available=True)
        try:
            payload = json.loads(output.read_text(encoding="utf-8"))
        except Exception:
            return _bounded_failure("EXPERIENCE_REGRESSION_EVIDENCE_INVALID", executor_available=True)
    if not isinstance(payload, Mapping):
        return _bounded_failure("EXPERIENCE_REGRESSION_EVIDENCE_INVALID", executor_available=True)
    if payload.get("schema") != "agentos.experience-regression/v1":
        return _bounded_failure("EXPERIENCE_REGRESSION_SCHEMA_INVALID", executor_available=True)
    if payload.get("project_id") != "agentos-core" or payload.get("executor") != EXECUTOR_CLASS:
        return _bounded_failure("EXPERIENCE_REGRESSION_IDENTITY_MISMATCH", executor_available=True)
    verdict = payload.get("verdict")
    if verdict not in {"PASS", "FAIL"}:
        return _bounded_failure("EXPERIENCE_REGRESSION_VERDICT_INVALID", executor_available=True)
    checks = payload.get("checks") if isinstance(payload.get("checks"), Mapping) else {}
    classification = payload.get("classification")
    if not isinstance(classification, str) or not classification:
        classification = "EXPERIENCE_REGRESSION_PASS" if verdict == "PASS" else "EXPERIENCE_REGRESSION_FAILED"
    if (proc.returncode == 0) != (verdict == "PASS"):
        classification = "EXPERIENCE_REGRESSION_EXIT_MISMATCH"
    credential_boundary_ok = payload.get("credential_exposed") is False
    successful = bool(proc.returncode == 0 and verdict == "PASS" and credential_boundary_ok)
    return {
        "experiment_id": payload.get("experiment_id"),
        "verdict": verdict,
        "baseline_score": _score(payload, "baseline"),
        "hydrated_score": _score(payload, "hydrated"),
        "uplift": payload.get("uplift") if isinstance(payload.get("uplift"), (int, float)) else None,
        "hydration_receipt_ok": checks.get("hydration_receipt_ok") is True,
        "classification": classification,
        "executor_available": True,
        "routable": True,
        "authorized": True,
        "successful": successful,
        "credential_exposed": not credential_boundary_ok,
    }


def register_issue117_provider_if_available(*, registry: ExecutorJobProviderRegistry = DEFAULT_PROVIDERS, runtime_root: str | Path | None = None) -> bool:
    root = Path(runtime_root) if runtime_root is not None else _runtime_root()
    if not provider_implementation_available(root):
        return False
    existing = registry.get(JOB_TYPE)
    if existing is not None:
        if existing.provider_id == PROVIDER_ID and existing.executor_class == EXECUTOR_CLASS:
            return True
        raise RuntimeError("experience.regression provider already registered differently")
    def handler(request: Mapping[str, Any]) -> Mapping[str, Any]:
        return run_issue117_experience_regression(request, runtime_root=root)
    registry.register(job_type=JOB_TYPE, provider_id=PROVIDER_ID, executor_class=EXECUTOR_CLASS, handler=handler)
    return True
