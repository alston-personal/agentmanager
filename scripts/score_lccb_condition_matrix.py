#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import statistics
import sys

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from research.lccb_evaluator import evaluate_stage
from research.lccb_synthetic import HiddenLabel


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--pack", required=True)
    p.add_argument("--responses", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--benchmark-id", default="lccb-condition-matrix-v1")
    args = p.parse_args()
    labels = tuple(HiddenLabel(**row) for row in _jsonl(Path(args.pack) / "private" / "labels.jsonl"))
    rows = _jsonl(Path(args.responses))
    groups: dict[tuple[str, str, int, int], list[dict]] = {}
    for row in rows:
        key = (str(row["condition"]), str(row["model"]), int(row["repeat"]), int(row["stage"]))
        groups.setdefault(key, []).append(row)

    results: list[dict] = []
    for (condition, model, repeat, stage), group in sorted(groups.items()):
        responses = {str(row["task_key"]): str(row["response_text"]) for row in group}
        result = evaluate_stage(labels, responses, benchmark_id=args.benchmark_id, stage=stage, model_ref=f"{model}:{condition}")
        first = group[0]
        results.append({
            "condition": condition,
            "model": model,
            "repeat": repeat,
            "stage": stage,
            "result_id": result.result_id,
            "prompt_characters": int(first.get("prompt_characters", 0)),
            "prompt_utf8_bytes": int(first.get("prompt_utf8_bytes", 0)),
            "metrics": asdict(result.metrics),
        })

    metric_names = sorted(results[0]["metrics"]) if results else []
    aggregates: list[dict] = []
    for condition in sorted({r["condition"] for r in results}):
        for stage in sorted({r["stage"] for r in results if r["condition"] == condition}):
            subset = [r for r in results if r["condition"] == condition and r["stage"] == stage]
            aggregates.append({
                "condition": condition,
                "stage": stage,
                "repeats": len(subset),
                "mean_prompt_characters": statistics.mean(float(r["prompt_characters"]) for r in subset),
                "mean_prompt_utf8_bytes": statistics.mean(float(r["prompt_utf8_bytes"]) for r in subset),
                "mean_metrics": {name: statistics.mean(float(r["metrics"][name]) for r in subset) for name in metric_names},
            })

    payload = {"schema_version": "agentos.lccb-condition-matrix-scored/v1", "benchmark_id": args.benchmark_id, "results": results, "aggregates": aggregates}
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
