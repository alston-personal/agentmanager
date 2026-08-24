#!/usr/bin/env python3
"""Build a frozen controlled LCCB pack with separate public/private artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from research.lccb_public_tasks import public_tasks_jsonl
from research.lccb_synthetic import (
    DEFAULT_SEED,
    STAGES,
    generate_pack,
    private_labels_jsonl,
    public_experience_jsonl,
)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output-dir", required=True)
    p.add_argument("--seed", type=int, default=DEFAULT_SEED)
    p.add_argument("--events", type=int, default=1000)
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        pack = generate_pack(seed=args.seed, event_count=args.events)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    root = Path(args.output_dir)
    public_dir = root / "public"
    private_dir = root / "private"
    public_dir.mkdir(parents=True, exist_ok=True)
    private_dir.mkdir(parents=True, exist_ok=True)

    experience_path = public_dir / "experience.jsonl"
    tasks_path = public_dir / "tasks.jsonl"
    private_path = private_dir / "labels.jsonl"
    experience_path.write_text(public_experience_jsonl(pack), encoding="utf-8")
    tasks_path.write_text(public_tasks_jsonl(pack.labels), encoding="utf-8")
    private_path.write_text(private_labels_jsonl(pack), encoding="utf-8")

    counts_by_stage = {
        str(stage): sum(1 for item in pack.labels if item.stage == stage)
        for stage in STAGES
        if stage == 0 or stage <= args.events
    }
    manifest = {
        "schema_version": "agentos.lccb-synthetic-manifest/v1",
        "seed": pack.seed,
        "event_count": len(pack.events),
        "label_count": len(pack.labels),
        "task_count_by_stage": counts_by_stage,
        "experience_manifest_hash": pack.experience_manifest_hash,
        "evaluator_manifest_hash": pack.evaluator_manifest_hash,
        "public_experience_artifact": "public/experience.jsonl",
        "public_tasks_artifact": "public/tasks.jsonl",
        "private_artifact": "private/labels.jsonl",
        "private_artifact_must_not_be_exposed_to_agent": True,
    }
    (root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
