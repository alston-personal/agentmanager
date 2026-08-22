#!/usr/bin/env python3
"""Score raw controlled-track LCCB responses using evaluator-only labels."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from research.lccb_evaluator import evaluate_stage
from research.lccb_synthetic import HiddenLabel


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--pack", required=True)
    p.add_argument("--responses", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--benchmark-id", default="lccb-controlled-v1")
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    root = Path(args.pack)
    labels_path = root / "private" / "labels.jsonl"
    if not labels_path.exists():
        print("private labels artifact not found", file=sys.stderr)
        return 2
    labels = tuple(HiddenLabel(**row) for row in _jsonl(labels_path))
    rows = _jsonl(Path(args.responses))
    if not rows:
        print("response artifact is empty", file=sys.stderr)
        return 2

    groups: dict[tuple[str, int, int], list[dict]] = {}
    for row in rows:
        key = (str(row["model"]), int(row["repeat"]), int(row["stage"]))
        groups.setdefault(key, []).append(row)

    results = []
    for (model, repeat, stage), group in sorted(groups.items(), key=lambda item: item[0]):
        responses = {str(row["task_key"]): str(row["response_text"]) for row in group}
        try:
            result = evaluate_stage(
                labels,
                responses,
                benchmark_id=args.benchmark_id,
                stage=stage,
                model_ref=model,
            )
        except ValueError as exc:
            print(f"scoring failed for model={model} repeat={repeat} stage={stage}: {exc}", file=sys.stderr)
            return 2
        results.append(
            {
                "model": model,
                "repeat": repeat,
                "stage": stage,
                "result_id": result.result_id,
                "metrics": asdict(result.metrics),
            }
        )

    payload = {
        "schema_version": "agentos.lccb-scored-series/v1",
        "benchmark_id": args.benchmark_id,
        "results": results,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
