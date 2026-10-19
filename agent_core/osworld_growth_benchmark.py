from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

RELEASE_SCHEMA = "agentos.external-benchmark-release/v1"
RUN_SCHEMA = "agentos.external-benchmark-run/v1"
COMPARISON_SCHEMA = "agentos.growth-proof-external-comparison/v1"
VALID_ARMS = {"raw", "cold", "experienced"}


def _stable_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_json(value: Any) -> str:
    return hashlib.sha256(_stable_json(value)).hexdigest()


def load_release(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema") != RELEASE_SCHEMA:
        raise ValueError(f"invalid release schema: {payload.get('schema')}")
    return payload


def parse_osworld_results(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("OSWorld summary/results.json must be a JSON array")
    rows = []
    score_sum = 0.0
    valid = 0
    errors = 0
    for row in payload:
        if not isinstance(row, dict):
            continue
        score = float(row.get("score") or 0.0)
        status = str(row.get("status") or "unknown")
        if status == "error":
            errors += 1
        rows.append(
            {
                "application": str(row.get("application") or ""),
                "task_id": str(row.get("task_id") or ""),
                "status": status,
                "score": score,
            }
        )
        score_sum += score
        valid += 1
    return {
        "task_count": valid,
        "score_sum": score_sum,
        "mean_score": (score_sum / valid if valid else 0.0),
        "error_count": errors,
        "rows": rows,
    }


def build_run_record(
    *,
    release: dict[str, Any],
    arm: str,
    results: dict[str, Any],
    model: dict[str, Any],
    runtime: dict[str, Any],
    cognitive_snapshot: dict[str, Any] | None = None,
    contamination: dict[str, Any] | None = None,
) -> dict[str, Any]:
    arm = str(arm).strip().lower()
    if arm not in VALID_ARMS:
        raise ValueError(f"invalid arm: {arm}")

    cognitive_snapshot = dict(cognitive_snapshot or {})
    contamination = dict(contamination or {})

    if arm == "cold" and cognitive_snapshot.get("experience_enabled"):
        raise ValueError("cold arm must not enable accumulated experience")
    if arm == "experienced":
        if not cognitive_snapshot.get("experience_enabled"):
            raise ValueError("experienced arm requires accumulated experience")
        if not cognitive_snapshot.get("snapshot_sha256"):
            raise ValueError("experienced arm requires cognitive snapshot hash")
        if contamination.get("heldout_answers_seen") is not False:
            raise ValueError("experienced arm requires explicit heldout_answers_seen=false")

    record = {
        "schema": RUN_SCHEMA,
        "benchmark": release["benchmark"],
        "release": release["release"],
        "release_fingerprint": sha256_json(release),
        "arm": arm,
        "model": dict(model),
        "runtime": dict(runtime),
        "cognitive_snapshot": cognitive_snapshot,
        "contamination": contamination,
        "metrics": {
            "task_count": int(results["task_count"]),
            "mean_score": float(results["mean_score"]),
            "error_count": int(results["error_count"]),
        },
        "task_results": list(results["rows"]),
    }
    record["run_sha256"] = sha256_json(record)
    return record


def _comparable(cold: dict[str, Any], experienced: dict[str, Any]) -> list[str]:
    mismatches: list[str] = []
    for key in ("benchmark", "release", "release_fingerprint"):
        if cold.get(key) != experienced.get(key):
            mismatches.append(key)
    for key in ("provider", "name", "version"):
        if (cold.get("model") or {}).get(key) != (experienced.get("model") or {}).get(key):
            mismatches.append(f"model.{key}")
    for key in ("provider", "image", "action_space", "observation_type", "max_steps"):
        if (cold.get("runtime") or {}).get(key) != (experienced.get("runtime") or {}).get(key):
            mismatches.append(f"runtime.{key}")
    cold_ids = [x.get("task_id") for x in cold.get("task_results") or []]
    exp_ids = [x.get("task_id") for x in experienced.get("task_results") or []]
    if cold_ids != exp_ids:
        mismatches.append("task_ids")
    return mismatches


def compare_growth(*, cold: dict[str, Any], experienced: dict[str, Any]) -> dict[str, Any]:
    if cold.get("arm") != "cold":
        raise ValueError("cold record must have arm=cold")
    if experienced.get("arm") != "experienced":
        raise ValueError("experienced record must have arm=experienced")
    mismatches = _comparable(cold, experienced)
    if mismatches:
        raise ValueError("non-comparable runs: " + ", ".join(mismatches))

    c = float((cold.get("metrics") or {}).get("mean_score") or 0.0)
    e = float((experienced.get("metrics") or {}).get("mean_score") or 0.0)
    delta = e - c

    cold_by_id = {x["task_id"]: x for x in cold.get("task_results") or []}
    exp_by_id = {x["task_id"]: x for x in experienced.get("task_results") or []}
    improved = regressed = unchanged = 0
    for task_id in cold_by_id:
        cs = float(cold_by_id[task_id].get("score") or 0.0)
        es = float(exp_by_id[task_id].get("score") or 0.0)
        if es > cs:
            improved += 1
        elif es < cs:
            regressed += 1
        else:
            unchanged += 1

    verdict = "G3_CANDIDATE" if delta > 0 and regressed == 0 else "NOT_G3"
    result = {
        "schema": COMPARISON_SCHEMA,
        "benchmark": cold["benchmark"],
        "release": cold["release"],
        "cold_run_sha256": cold["run_sha256"],
        "experienced_run_sha256": experienced["run_sha256"],
        "controlled_variables": {
            "release": cold["release"],
            "model": cold["model"],
            "runtime": cold["runtime"],
            "task_ids_identical": True,
        },
        "changed_variable": "validated AgentOS cognitive snapshot",
        "metrics": {
            "cold_mean_score": c,
            "experienced_mean_score": e,
            "growth_uplift_absolute": delta,
            "improved_tasks": improved,
            "regressed_tasks": regressed,
            "unchanged_tasks": unchanged,
        },
        "verdict": verdict,
        "note": "External benchmark uplift is a G3 candidate; contamination and independent evidence still require audit.",
    }
    result["comparison_sha256"] = sha256_json(result)
    return result
