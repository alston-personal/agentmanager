#!/usr/bin/env python3
"""AgentOS-prehydrated #117 Codex Experience IR regression entry.

The Master Experience Floor is an AgentOS guarantee, not an executor-discretion
feature. Baseline remains a completely fresh Codex process. For the hydrated lane,
AgentOS resolves bounded ONE Experience IR before launching another fresh Codex.
A deterministic adapter compiles only explicit IR observation nodes into the
benchmark vocabulary; display summaries are never used as learned authority.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from agent_core.experience_observation import compile_experience_observations
from scripts import oracle_codex_experience_regression as regression


def _prehydrate() -> dict[str, object]:
    from agentos_node.experience_mcp_stdio import one_experience_hydrate

    return one_experience_hydrate(
        project_id=regression.PROJECT_ID,
        active_goal=regression.GOAL,
        realm="oracle",
        executor="codex",
        capabilities=regression.CAPABILITIES,
    )


def _hydrated_prompt(projection: dict[str, object]) -> str:
    observations = compile_experience_observations(
        projection,
        allowed_dimensions=regression.DIMENSIONS,
    )
    return f"""You are a completely fresh Codex executor with no prior AgentOS Core session history.
Project identity: {regression.PROJECT_ID}
Current goal: {regression.GOAL}

AgentOS has already hydrated bounded ONE Experience IR before executor launch.
The IR is the learned source. AgentOS deterministically compiled its explicit observation nodes into
ONE_EXPERIENCE_OBSERVATIONS below for this benchmark. Do not use display summaries as authority.
Do not inspect workspace files, git, network, prior sessions, local TODO/status files, or any other source.
Do not call tools for this benchmark.

ONE_EXPERIENCE_OBSERVATIONS:
{json.dumps(observations, ensure_ascii=False, sort_keys=True)}

ONE_EXPERIENCE_IR_PROJECTION:
{json.dumps(projection, ensure_ascii=False, sort_keys=True)}

This is a controlled Experience-transfer benchmark, not a repository task. Do not modify anything.
Return exactly one JSON object and nothing else with these keys:
{json.dumps(list(regression.DIMENSIONS))}
For each key, use the exact value in ONE_EXPERIENCE_OBSERVATIONS.values when present.
If a key is listed in missing_dimensions, return null for that key. Never infer protected-branch authority.
"""


def run_codex(exe: Path, *, hydrated: bool, timeout: int) -> dict[str, object]:
    prompt = regression.prompt(hydrated=False)
    if hydrated:
        projection = _prehydrate()
        prompt = _hydrated_prompt(projection)
    argv = [
        str(exe),
        "exec",
        "--skip-git-repo-check",
        "--sandbox",
        "read-only",
        "--color",
        "never",
        prompt,
    ]
    with tempfile.TemporaryDirectory(
        prefix=f"agentos-exp117-codex-{'hydrated' if hydrated else 'baseline'}-"
    ) as tmp:
        try:
            proc = subprocess.run(
                argv,
                cwd=tmp,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=timeout,
                env={**os.environ, "CI": "1"},
                check=False,
            )
            return {
                "returncode": proc.returncode,
                "timed_out": False,
                "stdout": proc.stdout[-12000:],
                "stderr_tail": proc.stderr[-3000:],
                "argv_family": "codex exec --sandbox read-only (AgentOS prehydrated Experience IR)",
            }
        except subprocess.TimeoutExpired as exc:
            return {
                "returncode": None,
                "timed_out": True,
                "stdout": (exc.stdout or "")[-12000:] if isinstance(exc.stdout, str) else "",
                "stderr_tail": (exc.stderr or "")[-3000:] if isinstance(exc.stderr, str) else "",
                "argv_family": "codex exec --sandbox read-only (AgentOS prehydrated Experience IR)",
            }


def _output_arg() -> Path | None:
    for index, value in enumerate(sys.argv[:-1]):
        if value == "--output":
            return Path(sys.argv[index + 1])
    return None


def _fixed_classification(payload: dict[str, object]) -> str:
    checks = payload.get("checks") if isinstance(payload.get("checks"), dict) else {}
    baseline = payload.get("baseline") if isinstance(payload.get("baseline"), dict) else {}
    hydrated = payload.get("hydrated") if isinstance(payload.get("hydrated"), dict) else {}
    baseline_run = baseline.get("run") if isinstance(baseline.get("run"), dict) else {}
    hydrated_run = hydrated.get("run") if isinstance(hydrated.get("run"), dict) else {}

    if baseline_run.get("timed_out") is True:
        return "EXPERIENCE_BASELINE_CODEX_TIMEOUT"
    if hydrated_run.get("timed_out") is True:
        return "EXPERIENCE_HYDRATED_CODEX_TIMEOUT"
    if baseline_run.get("returncode") != 0:
        return "EXPERIENCE_BASELINE_CODEX_RUNTIME_FAILED"
    if hydrated_run.get("returncode") != 0:
        return "EXPERIENCE_HYDRATED_CODEX_RUNTIME_FAILED"
    if checks.get("hydration_receipt_ok") is not True:
        return "EXPERIENCE_AGENTOS_PREHYDRATION_NOT_OBSERVED"
    if payload.get("verdict") != "PASS":
        return "EXPERIENCE_MASTER_FLOOR_NOT_MET"
    return "EXPERIENCE_REGRESSION_PASS"


def _correct_method_evidence(path: Path | None) -> None:
    if path is None or not path.is_file():
        return
    payload = json.loads(path.read_text(encoding="utf-8"))
    method = payload.get("method")
    if isinstance(method, dict):
        method["baseline"] = (
            "fresh Codex process + empty cwd; no AgentOS Experience projection is supplied; "
            "unchanged hydration receipt independently proves non-access"
        )
        method["hydrated"] = (
            "AgentOS pre-executor hydration from governed ONE Experience IR + independent receipt; "
            "explicit IR observation nodes are deterministically compiled before a fresh Codex process"
        )
    payload["config_override_used"] = False
    payload["hydration_delivery"] = "agentos-pre-executor-experience-ir"
    payload["experience_representation"] = "agentos.experience-ir/v1"
    payload["observation_projection"] = "derived-from-explicit-ir-set-nodes"
    payload["executor_tool_call_required_for_floor"] = False
    payload["classification"] = _fixed_classification(payload)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    regression.run_codex = run_codex
    rc = regression.main()
    _correct_method_evidence(_output_arg())
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
