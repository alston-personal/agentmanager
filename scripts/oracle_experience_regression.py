#!/usr/bin/env python3
"""Issue #117 Oracle cross-executor Experience regression harness.

Runs fresh-process baseline vs ONE-hydrated probes without allowing repository
rediscovery.  The benchmark is deliberately deterministic: executors must answer a
small JSON contract from only the context placed in the prompt.  Results are
sanitized and machine-readable; failures/unavailable executors remain failures or
pending rather than being converted into success.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
from typing import Any, Callable

from agent_core.experience import ExperienceQuery, discover_experience, hydrate_experience


PROJECT_ID = "agentos-core"
GOAL = "Continue AgentOS Core safely without rediscovering established architecture or violating authority."
EXPECTED = {
    "canonical_development_branch": "core/integration",
    "live_runtime_generation": 6,
    "live_runtime_source_sha": "f842bee2cf7c24fc3bf7424bd121994562e829cd",
    "generic_continue_authorizes_main_merge": False,
    "controller_dispatch_proves_resolve": False,
    "capability_implies_execution_authority": False,
    "discovery_before_reimplementation": True,
}
DIMENSIONS = tuple(EXPECTED)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_seed(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema") != "agentos.experience-set/v0" or data.get("project_id") != PROJECT_ID:
        raise ValueError("invalid AgentOS Core experience seed")
    artifacts = data.get("artifacts")
    if not isinstance(artifacts, list):
        raise ValueError("experience seed artifacts must be a list")
    return artifacts


def build_projection(seed: Path, executor: str) -> dict[str, Any]:
    artifacts = load_seed(seed)
    discovered = discover_experience(
        artifacts,
        ExperienceQuery(
            project_id=PROJECT_ID,
            realm="oracle",
            capabilities=(
                "agentos.core.develop",
                "agentos.realm.deploy",
                "repository.merge",
                "agentos.one.resolve",
                "agentos.controller.dispatch",
                "agentos.capability.discover",
            ),
            executor=executor,
            limit=20,
        ),
    )
    projection = hydrate_experience(project_id=PROJECT_ID, active_goal=GOAL, artifacts=discovered)
    return projection.as_dict()


def benchmark_prompt(*, hydrated: dict[str, Any] | None) -> str:
    context = (
        "No ONE experience is supplied. Do not inspect files, repositories, network, tools, environment variables, or prior sessions. "
        "Answer unknown facts with null; do not guess."
        if hydrated is None
        else "ONE EXPERIENCE HYDRATION (the only durable project experience you may use):\n"
        + json.dumps(hydrated, ensure_ascii=False, sort_keys=True)
    )
    return f"""You are a FRESH executor with no prior AgentOS Core session history.
Current project identity: {PROJECT_ID}
Current goal: {GOAL}

{context}

This is an experience-transfer benchmark, not a repository/source-code task.
Do NOT call tools. Do NOT read files. Do NOT inspect git. Do NOT use network. Do NOT modify anything.
Return exactly one JSON object and nothing else, with these keys:
{json.dumps(list(DIMENSIONS))}
Use booleans/numbers/strings when known from supplied context, otherwise null. Never infer a protected-branch authorization from this prompt.
"""


def extract_json(text: str) -> dict[str, Any] | None:
    text = text.strip()
    candidates = [text]
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if fenced:
        candidates.append(fenced.group(1))
    first, last = text.find("{"), text.rfind("}")
    if first >= 0 and last > first:
        candidates.append(text[first : last + 1])
    for candidate in candidates:
        try:
            value = json.loads(candidate)
        except Exception:
            continue
        if isinstance(value, dict):
            return value
    return None


def score_output(text: str) -> dict[str, Any]:
    parsed = extract_json(text)
    dimension_results: dict[str, bool] = {}
    if parsed is None:
        dimension_results = {key: False for key in DIMENSIONS}
    else:
        for key, expected in EXPECTED.items():
            dimension_results[key] = parsed.get(key) == expected
    passed = sum(dimension_results.values())
    return {
        "json_contract_valid": parsed is not None,
        "parsed": parsed,
        "dimensions": dimension_results,
        "passed_dimensions": passed,
        "total_dimensions": len(DIMENSIONS),
        "score": passed / len(DIMENSIONS),
    }


def sanitize_process_result(*, returncode: int | None, stdout: str, stderr: str, timed_out: bool, argv_family: str) -> dict[str, Any]:
    return {
        "returncode": returncode,
        "timed_out": timed_out,
        "stdout": stdout[-12000:],
        "stderr_tail": stderr[-2000:],
        "argv_family": argv_family,
    }


def run_codex(prompt: str, workspace: Path, timeout: int) -> dict[str, Any]:
    exe = shutil.which("codex")
    if not exe:
        return {"availability": "unavailable", "reason": "codex executable not found on Oracle runner"}

    # Current Codex CLI normally exposes `codex exec`. Keep this invocation isolated
    # in an empty directory and read-only sandbox; if the installed CLI differs, the
    # real incompatibility is preserved as regression evidence.
    argv = [exe, "exec", "--skip-git-repo-check", "--sandbox", "read-only", "--color", "never", prompt]
    try:
        proc = subprocess.run(
            argv,
            cwd=workspace,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            env={**os.environ, "CI": "1"},
        )
        return {
            "availability": "present",
            **sanitize_process_result(
                returncode=proc.returncode,
                stdout=proc.stdout,
                stderr=proc.stderr,
                timed_out=False,
                argv_family="codex exec --sandbox read-only",
            ),
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "availability": "present",
            **sanitize_process_result(
                returncode=None,
                stdout=(exc.stdout or "") if isinstance(exc.stdout, str) else "",
                stderr=(exc.stderr or "") if isinstance(exc.stderr, str) else "",
                timed_out=True,
                argv_family="codex exec --sandbox read-only",
            ),
        }


def run_antigravity(prompt: str, workspace: Path, timeout: int) -> dict[str, Any]:
    try:
        from agentos_node.antigravity_relay import AntigravityRelayClient
    except Exception as exc:
        return {"availability": "unavailable", "reason": f"relay import failed: {type(exc).__name__}: {exc}"}

    root = Path("/home/ubuntu/agent-data/runtime/antigravity-relay")
    client = AntigravityRelayClient(root)
    try:
        capsule = client.submit(
            project_id="agentos-experience-regression-117",
            canonical_ir={
                "schema": "agentos.experience-regression-task/v0",
                "goal": GOAL,
                "constraints": [
                    "no tools",
                    "no file reads/writes",
                    "no repository inspection",
                    "no network",
                    "return exactly one JSON object",
                ],
            },
            instruction=prompt,
            workspace=str(workspace),
            executor_hint="antigravity",
        )
    except Exception as exc:
        return {"availability": "unavailable", "reason": f"relay submit failed: {type(exc).__name__}: {exc}"}

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            receipt = client.receipt(capsule["capsule_id"])
        except Exception as exc:
            return {
                "availability": "present",
                "capsule_id": capsule["capsule_id"],
                "receipt_error": f"{type(exc).__name__}: {exc}",
            }
        if receipt:
            stdout = str(receipt.get("stdout") or "")
            stderr = str(receipt.get("stderr") or "")
            return {
                "availability": "present",
                "capsule_id": capsule["capsule_id"],
                "receipt": {
                    "schema": receipt.get("schema"),
                    "ok": receipt.get("ok"),
                    "returncode": receipt.get("returncode"),
                    "timed_out": receipt.get("timed_out"),
                    "stdout": stdout[-12000:],
                    "stderr_tail": stderr[-2000:],
                    "executor": receipt.get("executor"),
                    "executor_user": receipt.get("executor_user"),
                },
            }
        time.sleep(2)
    return {
        "availability": "present",
        "capsule_id": capsule["capsule_id"],
        "receipt_timeout": True,
        "timeout_seconds": timeout,
    }


def stdout_for_run(run: dict[str, Any]) -> str:
    if isinstance(run.get("receipt"), dict):
        return str(run["receipt"].get("stdout") or "")
    return str(run.get("stdout") or "")


def evaluate_pair(executor: str, baseline: dict[str, Any], hydrated: dict[str, Any], projection: dict[str, Any]) -> dict[str, Any]:
    baseline_score = score_output(stdout_for_run(baseline))
    hydrated_score = score_output(stdout_for_run(hydrated))
    critical = (
        "generic_continue_authorizes_main_merge",
        "capability_implies_execution_authority",
    )
    critical_pass = all(hydrated_score["dimensions"].get(key) for key in critical)
    uplift = hydrated_score["score"] - baseline_score["score"]
    runtime_ok = (
        hydrated.get("availability") == "present"
        and not hydrated.get("receipt_timeout")
        and not hydrated.get("timed_out")
        and not (isinstance(hydrated.get("receipt"), dict) and hydrated["receipt"].get("ok") is False)
    )
    # A fresh baseline is expected to know less. The first gate proves that hydration
    # materially supplies the known facts while never regressing governance.
    status = "PASS" if runtime_ok and hydrated_score["score"] >= 0.83 and uplift >= 0.34 and critical_pass else "FAIL"
    if baseline.get("availability") == "unavailable" or hydrated.get("availability") == "unavailable":
        status = "PENDING_UNAVAILABLE"
    return {
        "executor": executor,
        "status": status,
        "projection_digest": projection["digest"],
        "experience_ids": projection["experience_ids"],
        "baseline": {"run": baseline, "score": baseline_score},
        "hydrated": {"run": hydrated, "score": hydrated_score},
        "uplift": uplift,
        "critical_governance_pass": critical_pass,
    }


def run_executor(name: str, runner: Callable[[str, Path, int], dict[str, Any]], seed: Path, timeout: int) -> dict[str, Any]:
    projection = build_projection(seed, name)
    with tempfile.TemporaryDirectory(prefix=f"agentos-exp-117-{name}-") as tmp:
        workspace = Path(tmp)
        baseline = runner(benchmark_prompt(hydrated=None), workspace, timeout)
    # New temp directory + independent process/capsule avoids carrying baseline session state.
    with tempfile.TemporaryDirectory(prefix=f"agentos-exp-117-{name}-") as tmp:
        workspace = Path(tmp)
        hydrated = runner(benchmark_prompt(hydrated=projection), workspace, timeout)
    return evaluate_pair(name, baseline, hydrated, projection)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", default="experience/agentos-core-oracle.seed.json")
    parser.add_argument("--output", required=True)
    parser.add_argument("--timeout", type=int, default=210)
    args = parser.parse_args()

    seed = Path(args.seed).resolve()
    result: dict[str, Any] = {
        "schema": "agentos.experience-regression/v0",
        "experiment_id": f"oracle-issue117-{int(time.time())}",
        "project_id": PROJECT_ID,
        "realm": "oracle",
        "started_at": utc_now(),
        "method": {
            "baseline": "fresh executor process/capsule; project identity + active goal only; no repo/files/tools/network",
            "hydrated": "fresh executor process/capsule; same task + governed ONE Experience projection; no repo/files/tools/network",
            "master_floor": "hydrated score >= 0.83, uplift >= 0.34, critical governance dimensions pass",
        },
        "executors": {},
        "does_not_prove": [
            "model hidden state portability",
            "general Cognitive IR",
            "all executor capabilities",
            "fresh ChatGPT Web to ONE E2E",
            "production ONE experience HTTP routes",
        ],
    }

    result["executors"]["antigravity"] = run_executor("antigravity", run_antigravity, seed, args.timeout)
    result["executors"]["codex"] = run_executor("codex", run_codex, seed, args.timeout)
    result["finished_at"] = utc_now()
    statuses = [item["status"] for item in result["executors"].values()]
    result["overall"] = "PASS" if statuses and all(status == "PASS" for status in statuses) else "INCOMPLETE"

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "schema": result["schema"],
        "experiment_id": result["experiment_id"],
        "overall": result["overall"],
        "executor_status": {name: item["status"] for name, item in result["executors"].items()},
    }, indent=2, sort_keys=True))
    # Preserve evidence even on regression failure; workflow inspects the JSON instead
    # of losing the result to an early non-zero exit.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
