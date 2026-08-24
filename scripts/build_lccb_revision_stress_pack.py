#!/usr/bin/env python3
"""Build a high-conflict LCCB pack that stresses full-history replay vs structured current state.

The pack deliberately makes nearly every public event a semantic revision. B1 must
recover the last authoritative value for each key from the complete ordered
history; B3 is built from exactly the same public history but exposes only the
latest public state per semantic key through the existing condition projector.
Evaluator-only labels remain physically separate from public experience/tasks.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path

SCHEMA = "agentos.lccb-revision-stress/v1"
DEFAULT_SEED = 73129
DEFAULT_EVENTS = 4000
DEFAULT_KEYS = 24
DEFAULT_STAGES = (0, 1000, 4000)


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash_rows(rows: list[dict]) -> str:
    return sha256(("\n".join(_canonical(row) for row in rows) + "\n").encode("utf-8")).hexdigest()


def _event(index: int, key: str, value: str, previous: str | None, revision: int) -> dict:
    if previous is None:
        content = f"Authoritative state established: {key} is {value}."
        kind = "state_observation"
    else:
        content = (
            f"Authoritative revision {revision}: {key} is now {value}; "
            f"the previous value {previous} is superseded and must not be used."
        )
        kind = "state_revision"
    return {
        "project_id": "lccb-meridian-revision-stress",
        "source_kind": "synthetic_benchmark",
        "source_ref": f"lccb:revision-stress:event:{index:07d}",
        "actor_kind": "benchmark_world",
        "event_kind": kind,
        "content": content,
        "occurred_at": "2026-02-01T00:00:00Z",
        "trust_class": "verified",
        "metadata": {
            "benchmark": SCHEMA,
            "sequence": index,
            "op": "set_fact",
            "key": key,
            "value": value,
            "revision": revision,
        },
    }


def _labels_for_stage(stage: int, keys: list[str], current: dict[str, str], sources: dict[str, str], history: dict[str, list[str]]) -> list[dict]:
    rows: list[dict] = []
    for key in keys:
        value = current.get(key)
        stale = tuple(v for v in history.get(key, ()) if v != value)
        rows.append({
            "task_key": f"stress-state:{key}",
            "category": "supersession_stress",
            "stage": stage,
            "prompt": (
                f"What is the current authoritative value of {key} after all supplied Project Meridian revisions? "
                "If the supplied history does not establish it, answer unknown."
            ),
            "expected_facts": [value] if value is not None else ["unknown"],
            "forbidden_facts": list(dict.fromkeys(stale)),
            "evidence_source_refs": [sources[key]] if value is not None else [],
        })
    return rows


def build_pack(*, event_count: int, key_count: int, stages: tuple[int, ...]) -> tuple[list[dict], list[dict], list[dict]]:
    if event_count < 1:
        raise ValueError("--events must be >= 1")
    if key_count < 2:
        raise ValueError("--key-count must be >= 2")
    if any(stage < 0 or stage > event_count for stage in stages):
        raise ValueError("all stages must be between 0 and --events")

    keys = [f"service-{i:02d}.owner" for i in range(1, key_count + 1)]
    current: dict[str, str] = {}
    sources: dict[str, str] = {}
    history: dict[str, list[str]] = {key: [] for key in keys}
    revision_count: dict[str, int] = {key: 0 for key in keys}
    events: list[dict] = []
    labels: list[dict] = []

    stage_set = set(stages)
    if 0 in stage_set:
        labels.extend(_labels_for_stage(0, keys, current, sources, history))

    for index in range(1, event_count + 1):
        key = keys[(index - 1) % key_count]
        previous = current.get(key)
        if previous is not None:
            history[key].append(previous)
        revision_count[key] += 1
        revision = revision_count[key]
        key_index = (index - 1) % key_count + 1
        value = f"owner-{key_index:02d}-r{revision:04d}"
        event = _event(index, key, value, previous, revision)
        events.append(event)
        current[key] = value
        sources[key] = event["source_ref"]
        if index in stage_set:
            labels.extend(_labels_for_stage(index, keys, current, sources, history))

    tasks = [
        {
            "task_key": row["task_key"],
            "category": row["category"],
            "stage": row["stage"],
            "prompt": row["prompt"],
        }
        for row in labels
    ]
    tasks.sort(key=lambda row: (int(row["stage"]), str(row["task_key"])))
    return events, tasks, labels


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output-dir", required=True)
    p.add_argument("--seed", type=int, default=DEFAULT_SEED, help="Recorded for series identity; generator is otherwise deterministic")
    p.add_argument("--events", type=int, default=DEFAULT_EVENTS)
    p.add_argument("--key-count", type=int, default=DEFAULT_KEYS)
    p.add_argument("--stages", default=",".join(str(x) for x in DEFAULT_STAGES))
    args = p.parse_args()
    stages = tuple(int(x.strip()) for x in args.stages.split(",") if x.strip())

    try:
        events, tasks, labels = build_pack(event_count=args.events, key_count=args.key_count, stages=stages)
    except ValueError as exc:
        p.error(str(exc))

    root = Path(args.output_dir)
    public = root / "public"
    private = root / "private"
    public.mkdir(parents=True, exist_ok=True)
    private.mkdir(parents=True, exist_ok=True)

    def write_jsonl(path: Path, rows: list[dict]) -> None:
        path.write_text("\n".join(_canonical(row) for row in rows) + "\n", encoding="utf-8")

    write_jsonl(public / "experience.jsonl", events)
    write_jsonl(public / "tasks.jsonl", tasks)
    write_jsonl(private / "labels.jsonl", labels)

    counts = {str(stage): sum(1 for row in labels if int(row["stage"]) == stage) for stage in stages}
    manifest = {
        "schema_version": SCHEMA,
        "seed": args.seed,
        "event_count": len(events),
        "semantic_revision_events": len(events),
        "key_count": args.key_count,
        "stages": list(stages),
        "task_count_by_stage": counts,
        "experience_manifest_hash": _hash_rows(events),
        "evaluator_manifest_hash": _hash_rows(labels),
        "public_experience_artifact": "public/experience.jsonl",
        "public_tasks_artifact": "public/tasks.jsonl",
        "private_artifact": "private/labels.jsonl",
        "private_artifact_must_not_be_exposed_to_agent": True,
        "experimental_question": "Does structured current state preserve current-value accuracy under a dense revision history where full-history replay must resolve thousands of superseded values?",
        "conditions": {
            "B1": "complete ordered public history; no truncation",
            "B3": "latest public semantic state per key derived from the identical public history",
        },
    }
    (root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
