from __future__ import annotations

import importlib.util
from pathlib import Path

from agent_core.executor_job_contract import canonical_experience_regression_request
from agentos_node.executor_job_adapter import ExecutorJobProviderRegistry, execute_registered_executor_job
from agentos_node.issue117_experience_provider import register_issue117_provider_if_available


ROOT = Path(__file__).resolve().parents[1]


def _write_runtime(root: Path, *, codex_available: bool = True, credential_exposed: bool = False) -> None:
    scripts = root / "scripts"
    scripts.mkdir(parents=True)
    if codex_available:
        find_codex = "return Path('/fixed/trusted/codex')"
    else:
        find_codex = "raise FileNotFoundError('not installed')"
    (scripts / "oracle_codex_experience_regression.py").write_text(
        "from pathlib import Path\n"
        "def find_codex():\n"
        f"    {find_codex}\n",
        encoding="utf-8",
    )
    (scripts / "oracle_codex_experience_regression_entry_v2.py").write_text(
        "import argparse, json, sys\n"
        "p=argparse.ArgumentParser()\n"
        "p.add_argument('--output', required=True)\n"
        "p.add_argument('--timeout')\n"
        "a=p.parse_args()\n"
        "payload={\n"
        " 'schema':'agentos.experience-regression/v1',\n"
        " 'experiment_id':'exp-provider-test',\n"
        " 'project_id':'agentos-core',\n"
        " 'executor':'openai-codex-local',\n"
        " 'baseline':{'score':{'score':0.25},'run':{'stdout':'PRIVATE MODEL OUTPUT'}},\n"
        " 'hydrated':{'score':{'score':1.0},'run':{'stderr_tail':'/home/ubuntu/private'}},\n"
        " 'checks':{'hydration_receipt_ok':True},\n"
        " 'uplift':0.75,\n"
        " 'verdict':'PASS',\n"
        f" 'credential_exposed':{credential_exposed!r}\n"
        "}\n"
        "open(a.output,'w',encoding='utf-8').write(json.dumps(payload))\n"
        "print('Bearer TOPSECRET /private/provider/stdout')\n"
        "print('secret stderr', file=sys.stderr)\n"
        "raise SystemExit(0)\n",
        encoding="utf-8",
    )


def _load_entry_v2():
    path = ROOT / "scripts" / "oracle_codex_experience_regression_entry_v2.py"
    spec = importlib.util.spec_from_file_location("_issue117_entry_v2_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_provider_is_not_registered_when_issue117_is_absent(tmp_path: Path) -> None:
    registry = ExecutorJobProviderRegistry()
    assert register_issue117_provider_if_available(registry=registry, runtime_root=tmp_path) is False
    assert registry.get("experience.regression") is None


def test_integrated_issue117_provider_returns_only_bounded_regression_evidence(tmp_path: Path) -> None:
    _write_runtime(tmp_path)
    registry = ExecutorJobProviderRegistry()
    assert register_issue117_provider_if_available(registry=registry, runtime_root=tmp_path) is True

    receipt = execute_registered_executor_job(
        job_id="job-provider-pass",
        request=canonical_experience_regression_request(),
        registry=registry,
    )
    assert receipt["executor_available"] is True
    assert receipt["routable"] is True
    assert receipt["authorized"] is True
    assert receipt["successful"] is True
    assert receipt["verdict"] == "PASS"
    assert receipt["baseline_score"] == 0.25
    assert receipt["hydrated_score"] == 1.0
    assert receipt["uplift"] == 0.75
    assert receipt["hydration_receipt_ok"] is True
    assert receipt["credential_exposed"] is False
    rendered = str(receipt)
    for forbidden in ("PRIVATE MODEL OUTPUT", "/home/ubuntu/private", "TOPSECRET", "/private/provider", "secret stderr"):
        assert forbidden not in rendered


def test_registered_provider_can_report_codex_executor_unavailable_independently(tmp_path: Path) -> None:
    _write_runtime(tmp_path, codex_available=False)
    registry = ExecutorJobProviderRegistry()
    assert register_issue117_provider_if_available(registry=registry, runtime_root=tmp_path) is True

    receipt = execute_registered_executor_job(
        job_id="job-provider-unavailable",
        request=canonical_experience_regression_request(),
        registry=registry,
    )
    assert receipt["executor_available"] is False
    assert receipt["routable"] is True
    assert receipt["authorized"] is True
    assert receipt["successful"] is False
    assert receipt["classification"] == "EXPERIENCE_CODEX_EXECUTOR_UNAVAILABLE"


def test_provider_credential_boundary_violation_is_forced_to_failure(tmp_path: Path) -> None:
    _write_runtime(tmp_path, credential_exposed=True)
    registry = ExecutorJobProviderRegistry()
    assert register_issue117_provider_if_available(registry=registry, runtime_root=tmp_path) is True

    receipt = execute_registered_executor_job(
        job_id="job-provider-credential",
        request=canonical_experience_regression_request(),
        registry=registry,
    )
    assert receipt["executor_available"] is True
    assert receipt["successful"] is False
    assert receipt["credential_exposed"] is False
    assert receipt["classification"] == "PROVIDER_CREDENTIAL_BOUNDARY_VIOLATION"


def test_v2_classifies_agentos_pre_hydration_and_floor_failures() -> None:
    entry = _load_entry_v2()
    payload = {
        "baseline": {"run": {"returncode": 0, "timed_out": False}},
        "hydrated": {"run": {"returncode": 0, "timed_out": False}},
        "checks": {"hydration_receipt_ok": False},
        "verdict": "FAIL",
    }
    assert entry._fixed_classification(payload) == "EXPERIENCE_AGENTOS_PREHYDRATION_NOT_OBSERVED"

    payload["checks"]["hydration_receipt_ok"] = True
    assert entry._fixed_classification(payload) == "EXPERIENCE_MASTER_FLOOR_NOT_MET"

    payload["verdict"] = "PASS"
    assert entry._fixed_classification(payload) == "EXPERIENCE_REGRESSION_PASS"


def test_v2_hydrated_prompt_uses_supplied_projection_without_requiring_tool_call() -> None:
    entry = _load_entry_v2()
    projection = {
        "schema": "agentos.experience-hydration/v0",
        "source": "ONE_EXPERIENCE",
        "project_id": "agentos-core",
        "items": [{"payload": {"canonical_development_branch": "core/integration"}}],
        "credential_exposed": False,
    }
    prompt = entry._hydrated_prompt(projection)
    assert "ONE_EXPERIENCE_PROJECTION" in prompt
    assert '"canonical_development_branch": "core/integration"' in prompt
    assert "Do not call tools for this benchmark" in prompt
    assert "must call agentos-experience" not in prompt
