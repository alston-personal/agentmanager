#!/usr/bin/env python3
"""Evaluator-side audit of B1/B2/B3 evidence selection for a frozen LCCB pack.

This analysis does not call a model. It asks a narrower representation question:
for each benchmark task, does the public evidence selected by a condition contain
the current authoritative source, stale same-key sources, both, or neither?

Private labels are read only by this evaluator-side script, never by a model
runner. The output is a mechanism audit and must not be reported as a cognitive
performance result.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable

from research.lccb_condition_prompts import _retrieved, _structured, _visible
from research.lccb_openai_compatible import tasks_for_stage


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _semantic_key(task_key: str) -> tuple[str | None, str | None]:
    if task_key.startswith("state:"):
        return "set_fact", task_key[len("state:"):]
    if task_key.startswith("procedure:"):
        return "set_procedure", task_key[len("procedure:"):]
    if task_key.startswith("governance:"):
        return "set_capability", task_key[len("governance:"):]
    if task_key == "continuity:next-work":
        return "set_work", None
    return None, None


def _condition_evidence(events: list[dict], tasks: list[dict], stage: int, condition: str) -> list[dict]:
    stage_tasks = list(tasks_for_stage(tasks, stage))
    visible = _visible(events, stage)
    if condition == "B1":
        return visible
    if condition == "B2":
        return _retrieved(visible, tuple(stage_tasks))
    if condition == "B3":
        return _structured(visible)
    raise ValueError(condition)


def _ref(event: dict) -> str:
    return str(event.get("source_ref", ""))


def _same_key_events(evidence: Iterable[dict], *, op: str, key: str | None) -> list[dict]:
    rows = []
    for event in evidence:
        meta = event.get("metadata", {})
        if str(meta.get("op", "")) != op:
            continue
        if key is not None and str(meta.get("key", "")) != key:
            continue
        rows.append(event)
    return rows


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--pack", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--stages", default="100,1000")
    p.add_argument("--conditions", default="B1,B2,B3")
    args = p.parse_args()

    root = Path(args.pack)
    events = _jsonl(root / "public" / "experience.jsonl")
    tasks = _jsonl(root / "public" / "tasks.jsonl")
    labels = _jsonl(root / "private" / "labels.jsonl")
    labels_by = {(int(row["stage"]), str(row["task_key"])): row for row in labels}
    stages = tuple(int(x.strip()) for x in args.stages.split(",") if x.strip())
    conditions = tuple(x.strip() for x in args.conditions.split(",") if x.strip())

    observations: list[dict] = []
    aggregates: list[dict] = []

    for stage in stages:
        stage_tasks = list(tasks_for_stage(tasks, stage))
        for condition in conditions:
            evidence = _condition_evidence(events, tasks, stage, condition)
            evidence_refs = {_ref(event) for event in evidence}
            condition_rows: list[dict] = []

            for task in stage_tasks:
                task_key = str(task["task_key"])
                label = labels_by[(stage, task_key)]
                current_refs = [str(x) for x in label.get("evidence_source_refs", [])]
                current_ref_set = set(current_refs)
                op, key = _semantic_key(task_key)
                same_key = _same_key_events(evidence, op=op, key=key) if op else []
                same_key_refs = {_ref(event) for event in same_key}

                if task_key == "continuity:next-work":
                    # Continuity intentionally has a multi-source proof set; report
                    # source coverage but do not classify other work-state sources
                    # as stale because several may be jointly relevant.
                    stale_same_key_refs: list[str] = []
                    current_present = bool(current_ref_set.intersection(evidence_refs)) if current_ref_set else False
                    all_current_present = current_ref_set.issubset(evidence_refs) if current_ref_set else False
                    state_class = "multi_source"
                else:
                    stale_same_key_refs = sorted(same_key_refs - current_ref_set)
                    current_present = bool(current_ref_set.intersection(evidence_refs)) if current_ref_set else False
                    all_current_present = current_ref_set.issubset(evidence_refs) if current_ref_set else False
                    if current_present and stale_same_key_refs:
                        state_class = "current_plus_stale"
                    elif current_present:
                        state_class = "current_only"
                    elif stale_same_key_refs:
                        state_class = "stale_only"
                    else:
                        state_class = "no_same_key_evidence"

                row = {
                    "stage": stage,
                    "condition": condition,
                    "task_key": task_key,
                    "category": str(task.get("category", "")),
                    "current_source_refs": current_refs,
                    "current_source_any_present": current_present,
                    "current_source_all_present": all_current_present,
                    "same_key_evidence_refs": sorted(same_key_refs),
                    "stale_same_key_refs": stale_same_key_refs,
                    "evidence_state": state_class,
                }
                observations.append(row)
                condition_rows.append(row)

            single_source = [row for row in condition_rows if row["evidence_state"] != "multi_source"]
            current_only = sum(row["evidence_state"] == "current_only" for row in single_source)
            current_plus_stale = sum(row["evidence_state"] == "current_plus_stale" for row in single_source)
            stale_only = sum(row["evidence_state"] == "stale_only" for row in single_source)
            no_same_key = sum(row["evidence_state"] == "no_same_key_evidence" for row in single_source)
            current_any = sum(bool(row["current_source_any_present"]) for row in single_source)
            aggregates.append({
                "stage": stage,
                "condition": condition,
                "selected_evidence_events": len(evidence),
                "single_source_tasks": len(single_source),
                "current_source_task_coverage": (current_any / len(single_source)) if single_source else 1.0,
                "current_only_tasks": current_only,
                "current_plus_stale_tasks": current_plus_stale,
                "stale_only_tasks": stale_only,
                "no_same_key_evidence_tasks": no_same_key,
                "continuity_current_source_coverage": next(
                    (
                        sum(ref in evidence_refs for ref in row["current_source_refs"]) / len(row["current_source_refs"])
                        if row["current_source_refs"] else 1.0
                    )
                    for row in condition_rows
                    if row["task_key"] == "continuity:next-work"
                ),
            })

    payload = {
        "schema_version": "agentos.lccb-evidence-selection-audit/v1",
        "analysis_type": "evaluator-side representation audit; no model calls",
        "pack_manifest": json.loads((root / "manifest.json").read_text(encoding="utf-8")),
        "conditions": list(conditions),
        "stages": list(stages),
        "aggregates": aggregates,
        "observations": observations,
        "claim_boundary": [
            "This audit measures selected public evidence, not model cognition.",
            "Private labels are used only evaluator-side to identify the canonical current source after selection.",
            "A stale-only evidence classification is a representation risk, not automatically a model error.",
            "Cognitive claims remain governed by the completed provider experiment scores."
        ],
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
