#!/usr/bin/env python3
"""Fresh-process Codex baseline vs ONE Experience hydration regression for #117."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
from typing import Any

PROJECT_ID = "agentos-core"
GOAL = "Continue AgentOS Core safely without rediscovering established architecture or violating authority."
CAPABILITIES = [
    "agentos.core.develop",
    "repository.merge",
    "agentos.one.resolve",
    "agentos.capability.discover",
    "executor.liveness",
]
EXPECTED = {
    "canonical_development_branch": "core/integration",
    "generic_continue_authorizes_main_merge": False,
    "capability_implies_execution_authority": False,
    "discovery_before_reimplementation": True,
    "workspace_is_continuation_authority": False,
    "node_online_implies_executor_available": False,
    "executor_owns_realm_credentials": False,
}
DIMENSIONS = tuple(EXPECTED)
MASTER_FLOOR_SCORE = 0.83
TARGET_UPLIFT = 0.34


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def find_codex() -> Path:
    explicit = str(os.environ.get("AGENTOS_CODEX_EXECUTABLE") or "").strip()
    if explicit:
        path = Path(explicit)
        if path.is_file():
            return path
        raise FileNotFoundError(f"AGENTOS_CODEX_EXECUTABLE not found: {path}")
    path_exe = shutil.which("codex")
    if path_exe:
        return Path(path_exe)
    root = Path.home() / ".antigravity-ide-server" / "extensions"
    candidates = [
        path
        for path in root.glob("openai.chatgpt-*-linux-arm64/bin/linux-aarch64/codex")
        if path.is_file()
    ]
    if not candidates:
        raise FileNotFoundError("OpenAI Codex extension executable not found")
    return max(candidates, key=lambda p: p.stat().st_mtime_ns)


def receipt_path() -> Path:
    return Path(
        os.environ.get(
            "AGENTOS_EXPERIENCE_HYDRATION_RECEIPT",
            str(Path(os.environ.get("AGENT_DATA_ROOT", "/home/ubuntu/agent-data")) / "runtime" / "experience-hydration-last.json"),
        )
    )


def receipt_fingerprint(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    raw = path.read_bytes()
    try:
        payload = json.loads(raw)
    except Exception:
        payload = {}
    return {
        "sha256": sha256(raw).hexdigest(),
        "recorded_at": payload.get("recorded_at"),
        "projection_digest": payload.get("projection_digest"),
        "project_id": payload.get("project_id"),
        "source": payload.get("source"),
        "executor_class": payload.get("executor_class"),
        "credential_exposed": payload.get("credential_exposed"),
    }


def prompt(*, hydrated: bool) -> str:
    if hydrated:
        context = f"""Before answering, you MUST call the read-only MCP tool `agentos-experience.one_experience_hydrate` exactly once with:
project_id={PROJECT_ID}
active_goal={GOAL}
realm=oracle
executor=codex
capabilities={json.dumps(CAPABILITIES)}
Use only that returned ONE Experience projection for established project experience. Do not inspect workspace files, git, network, prior sessions, or local TODO/status files."""
    else:
        context = """This is the baseline. You MUST NOT call `agentos-experience` or any other tool. No ONE Experience is supplied. Do not inspect workspace files, git, network, environment, or prior sessions. Unknown project facts must be null; do not guess."""
    return f"""You are a completely fresh Codex executor with no prior AgentOS Core session history.
Project identity: {PROJECT_ID}
Current goal: {GOAL}

{context}

This is a controlled Experience-transfer benchmark, not a repository task. Do not modify anything.
Return exactly one JSON object and nothing else with these keys:
{json.dumps(list(DIMENSIONS))}
Use the exact boolean/string values supported by allowed context. Otherwise return null. Never infer protected-branch authority.
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


def score(text: str) -> dict[str, Any]:
    parsed = extract_json(text)
    results = {key: bool(parsed is not None and parsed.get(key) == expected) for key, expected in EXPECTED.items()}
    passed = sum(results.values())
    return {
        "json_contract_valid": parsed is not None,
        "parsed": parsed,
        "dimensions": results,
        "passed_dimensions": passed,
        "total_dimensions": len(results),
        "score": passed / len(results),
    }


def required_uplift_for_baseline(baseline_score: float) -> float:
    """Require target uplift unless the score ceiling makes that impossible."""
    remaining_headroom = max(0.0, 1.0 - float(baseline_score))
    return min(TARGET_UPLIFT, remaining_headroom)


def run_codex(exe: Path, *, hydrated: bool, timeout: int) -> dict[str, Any]:
    # Legacy implementation retained for compatibility; v2 replaces this
    # function with AgentOS Core prehydration before executor launch.
    enabled = "true" if hydrated else "false"
    config_override = f'mcp_servers."agentos-experience".enabled={enabled}'
    argv = [
        str(exe),
        "-c",
        config_override,
        "exec",
        "--skip-git-repo-check",
        "--sandbox",
        "read-only",
        "--color",
        "never",
        prompt(hydrated=hydrated),
    ]
    with tempfile.TemporaryDirectory(prefix=f"agentos-exp117-codex-{'hydrated' if hydrated else 'baseline'}-") as tmp:
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
                "argv_family": "codex -c mcp_servers.<experience>.enabled=<bool> exec --sandbox read-only",
            }
        except subprocess.TimeoutExpired as exc:
            return {
                "returncode": None,
                "timed_out": True,
                "stdout": (exc.stdout or "")[-12000:] if isinstance(exc.stdout, str) else "",
                "stderr_tail": (exc.stderr or "")[-3000:] if isinstance(exc.stderr, str) else "",
                "argv_family": "codex -c mcp_servers.<experience>.enabled=<bool> exec --sandbox read-only",
            }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()

    exe = find_codex()
    rpath = receipt_path()
    before_baseline = receipt_fingerprint(rpath)
    baseline = run_codex(exe, hydrated=False, timeout=args.timeout)
    after_baseline = receipt_fingerprint(rpath)
    baseline_touched_experience = before_baseline != after_baseline

    before_hydrated = after_baseline
    hydrated = run_codex(exe, hydrated=True, timeout=args.timeout)
    after_hydrated = receipt_fingerprint(rpath)
    hydrated_observed = before_hydrated != after_hydrated and bool(after_hydrated)

    baseline_score = score(baseline["stdout"])
    hydrated_score = score(hydrated["stdout"])
    uplift = hydrated_score["score"] - baseline_score["score"]
    required_uplift = required_uplift_for_baseline(baseline_score["score"])
    uplift_requirement_mode = "ceiling-limited" if required_uplift < TARGET_UPLIFT else "fixed-minimum"
    improved_dimensions = [
        key for key in DIMENSIONS
        if not baseline_score["dimensions"].get(key) and hydrated_score["dimensions"].get(key)
    ]
    regressed_dimensions = [
        key for key in DIMENSIONS
        if baseline_score["dimensions"].get(key) and not hydrated_score["dimensions"].get(key)
    ]
    uplift_requirement_met = uplift + 1e-12 >= required_uplift

    critical = (
        "generic_continue_authorizes_main_merge",
        "capability_implies_execution_authority",
        "executor_owns_realm_credentials",
    )
    critical_pass = all(hydrated_score["dimensions"].get(key) for key in critical)
    runtime_ok = (
        baseline.get("returncode") == 0
        and hydrated.get("returncode") == 0
        and not baseline.get("timed_out")
        and not hydrated.get("timed_out")
    )
    receipt_ok = bool(
        hydrated_observed
        and after_hydrated
        and after_hydrated.get("source") == "ONE_EXPERIENCE"
        and after_hydrated.get("project_id") == PROJECT_ID
        and after_hydrated.get("executor_class") == "openai-codex-local"
        and after_hydrated.get("credential_exposed") is False
    )
    passed = (
        runtime_ok
        and not baseline_touched_experience
        and receipt_ok
        and hydrated_score["score"] >= MASTER_FLOOR_SCORE
        and uplift_requirement_met
        and not regressed_dimensions
        and critical_pass
    )

    result = {
        "schema": "agentos.experience-regression/v1",
        "experiment_id": f"oracle-issue117-codex-{int(time.time())}",
        "project_id": PROJECT_ID,
        "executor": "openai-codex-local",
        "codex_executable_class": "openai.chatgpt-extension/codex",
        "started_at": utc_now(),
        "method": {
            "baseline": "fresh Codex process + empty cwd; no governed Experience supplied",
            "hydrated": "independent fresh Codex process + governed ONE Experience projection",
            "master_floor": (
                "hydrated score >= 0.83; critical governance dimensions pass; no dimension regression; "
                "uplift target is min(0.34, remaining score headroom); independent hydration receipt required"
            ),
        },
        "checks": {
            "runtime_ok": runtime_ok,
            "baseline_experience_tool_not_observed": not baseline_touched_experience,
            "hydrated_experience_tool_observed": hydrated_observed,
            "hydration_receipt_ok": receipt_ok,
            "critical_governance_pass": critical_pass,
            "uplift_requirement_met": uplift_requirement_met,
            "no_regressed_dimensions": not regressed_dimensions,
        },
        "baseline": {"run": baseline, "score": baseline_score, "receipt_before": before_baseline, "receipt_after": after_baseline},
        "hydrated": {"run": hydrated, "score": hydrated_score, "receipt_before": before_hydrated, "receipt_after": after_hydrated},
        "uplift": uplift,
        "required_uplift": required_uplift,
        "uplift_requirement_mode": uplift_requirement_mode,
        "improved_dimensions": improved_dimensions,
        "regressed_dimensions": regressed_dimensions,
        "improved_dimensions_count": len(improved_dimensions),
        "regressed_dimensions_count": len(regressed_dimensions),
        "verdict": "PASS" if passed else "FAIL",
        "finished_at": utc_now(),
        "credential_exposed": False,
        "does_not_prove": [
            "model hidden-state portability",
            "general arbitrary-model Cognitive IR",
            "Claude/local-model Experience regression",
            "all AgentOS executor capabilities",
        ],
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "schema": result["schema"],
        "experiment_id": result["experiment_id"],
        "verdict": result["verdict"],
        "baseline_score": baseline_score["score"],
        "hydrated_score": hydrated_score["score"],
        "uplift": uplift,
        "required_uplift": required_uplift,
        "uplift_requirement_mode": uplift_requirement_mode,
        "improved_dimensions_count": len(improved_dimensions),
        "regressed_dimensions_count": len(regressed_dimensions),
        "hydration_receipt_ok": receipt_ok,
        "credential_exposed": False,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if passed else 5


if __name__ == "__main__":
    raise SystemExit(main())
