#!/usr/bin/env python3
"""Fixed B-minus-Ei counterfactual for #117 branch-authority attribution.

This is deliberately not a generic Experience filter. The withheld Experience ID,
target dimension, executor, query, and repeat count are fixed in trusted source.
The accepted ONE Experience store is read-only; counterfactual projections exist
only in memory and never replace accepted state or the normal hydration receipt.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Any

from agent_core.experience import ExperienceQuery, hydrate_experience
from agent_core.experience_store import discover_from_one
from scripts import oracle_codex_experience_regression as regression
from scripts import oracle_codex_experience_regression_entry_v2 as entry_v2

WITHHELD_EXPERIENCE_ID = "core.branch-authority.v2"
TARGET_DIMENSION = "canonical_development_branch"
REPEAT_COUNT = 3


def counterfactual_projection() -> dict[str, Any]:
    query = ExperienceQuery(
        project_id=regression.PROJECT_ID,
        realm="oracle",
        capabilities=tuple(regression.CAPABILITIES),
        executor="codex",
        limit=20,
    )
    discovered = discover_from_one(query)
    ids = [str(item.get("experience_id") or "") for item in discovered]
    if WITHHELD_EXPERIENCE_ID not in ids:
        raise ValueError("fixed ablation target is not present in discovered ONE Experience")
    filtered = [item for item in discovered if item.get("experience_id") != WITHHELD_EXPERIENCE_ID]
    projection = hydrate_experience(
        project_id=regression.PROJECT_ID,
        active_goal=regression.GOAL,
        artifacts=filtered,
    ).as_dict()
    projection["source"] = "ONE_EXPERIENCE_ABLATION"
    projection["ablation"] = {"withheld_experience_id": WITHHELD_EXPERIENCE_ID}
    projection["credential_exposed"] = False
    return projection


def run_codex_with_projection(exe: Path, projection: dict[str, Any], *, timeout: int) -> dict[str, Any]:
    argv = [
        str(exe),
        "exec",
        "--skip-git-repo-check",
        "--sandbox",
        "read-only",
        "--color",
        "never",
        entry_v2._hydrated_prompt(projection),
    ]
    with tempfile.TemporaryDirectory(prefix="agentos-exp117-ablation-") as tmp:
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
            }
        except subprocess.TimeoutExpired as exc:
            return {
                "returncode": None,
                "timed_out": True,
                "stdout": (exc.stdout or "")[-12000:] if isinstance(exc.stdout, str) else "",
            }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()

    projection = counterfactual_projection()
    exe = regression.find_codex()
    target_values: list[Any] = []
    target_passes: list[bool] = []
    run_ok = True
    for _ in range(REPEAT_COUNT):
        run = run_codex_with_projection(exe, projection, timeout=args.timeout)
        if run.get("returncode") != 0 or run.get("timed_out") is True:
            run_ok = False
            target_values.append(None)
            target_passes.append(False)
            continue
        scored = regression.score(str(run.get("stdout") or ""))
        parsed = scored.get("parsed") if isinstance(scored.get("parsed"), dict) else {}
        target_values.append(parsed.get(TARGET_DIMENSION))
        target_passes.append(bool(scored.get("dimensions", {}).get(TARGET_DIMENSION)))

    if all(not value for value in target_passes):
        effect = "lost-improvement"
        confidence = "supported"
    elif all(target_passes):
        effect = "retained-improvement"
        confidence = "no-observed-effect"
    else:
        effect = "mixed"
        confidence = "ambiguous"

    payload = {
        "schema": "agentos.experience-ablation/v1",
        "project_id": regression.PROJECT_ID,
        "executor": "openai-codex-local",
        "withheld_experience_id": WITHHELD_EXPERIENCE_ID,
        "target_dimension": TARGET_DIMENSION,
        "projection_digest": projection.get("digest"),
        "remaining_experience_ids": list(projection.get("experience_ids") or []),
        "repeat_count": REPEAT_COUNT,
        "run_ok": run_ok,
        "target_values": target_values,
        "target_passes": target_passes,
        "effect": effect,
        "confidence": confidence,
        "credential_exposed": False,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "schema": payload["schema"],
        "withheld_experience_id": WITHHELD_EXPERIENCE_ID,
        "target_dimension": TARGET_DIMENSION,
        "repeat_count": REPEAT_COUNT,
        "run_ok": run_ok,
        "effect": effect,
        "confidence": confidence,
        "credential_exposed": False,
    }, sort_keys=True))
    return 0 if run_ok else 5


if __name__ == "__main__":
    raise SystemExit(main())
