#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from research.master_blind_evaluator import ExecutorEvent, evaluate_blind_trace
from research.master_blind_trial import BlindTrial, HiddenTrialKey, TrialStep


def _load_trial(path: Path) -> BlindTrial:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return BlindTrial(
        schema=raw["schema"],
        trial_id=raw["trial_id"],
        seed=int(raw["seed"]),
        goal=raw["goal"],
        public_steps=tuple(TrialStep(**item) for item in raw["public_steps"]),
    )


def _load_key(path: Path) -> HiddenTrialKey:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return HiddenTrialKey(
        schema=raw["schema"],
        trial_id=raw["trial_id"],
        expected_safe_order=tuple(raw["expected_safe_order"]),
        authority_boundary_step=raw["authority_boundary_step"],
        recoverable_failure_step=raw["recoverable_failure_step"],
        stale_step=raw["stale_step"],
        minimum_material_actions=int(raw["minimum_material_actions"]),
    )


def _load_events(path: Path) -> tuple[ExecutorEvent, ...]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    items = raw.get("events") if isinstance(raw, dict) else raw
    if not isinstance(items, list):
        raise ValueError("trace JSON must be a list or an object containing events")
    return tuple(ExecutorEvent(**item) for item in items)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--public", required=True)
    parser.add_argument("--hidden", required=True)
    parser.add_argument("--trace", required=True)
    parser.add_argument("--output")
    args = parser.parse_args()

    score = evaluate_blind_trace(
        _load_trial(Path(args.public)),
        _load_key(Path(args.hidden)),
        _load_events(Path(args.trace)),
    )
    payload = asdict(score)
    text = json.dumps(payload, indent=2, sort_keys=True)
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if score.master_grade_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
