"""Public-only prompt construction for the controlled LCCB B0-B3 comparison."""
from __future__ import annotations

import json
from collections import defaultdict

from research.lccb_openai_compatible import canonical_json, tasks_for_stage

SYSTEM = (
    "You are participating in a controlled longitudinal cognition benchmark. "
    "Use only the supplied public evidence. For each task return the current answer and include the public source_ref(s) that support it. "
    "If evidence does not establish an answer, answer exactly 'unknown'. Do not invent facts. "
    "Return only one JSON object mapping every task_key to a concise string answer."
)


def _visible(events: list[dict], stage: int) -> list[dict]:
    return [e for e in events if int(e.get("metadata", {}).get("sequence", 0)) <= stage]


def _task_terms(task: dict) -> set[str]:
    key = str(task["task_key"])
    terms = set(key.replace(":", " ").replace("-", " ").split())
    terms.update(str(task.get("prompt", "")).lower().replace("?", " ").replace(":", " ").split())
    return {t.lower() for t in terms if len(t) >= 3}


def _event_text(event: dict) -> str:
    return canonical_json(event).lower()


def _retrieved(events: list[dict], tasks: tuple[dict, ...], *, top_k: int = 16) -> list[dict]:
    scored: dict[str, tuple[int, int, dict]] = {}
    task_terms = [term for task in tasks for term in _task_terms(task)]
    for event in events:
        text = _event_text(event)
        score = sum(1 for term in task_terms if term in text)
        if score <= 0:
            continue
        seq = int(event.get("metadata", {}).get("sequence", 0))
        ref = str(event.get("source_ref", f"seq:{seq}"))
        scored[ref] = (score, seq, event)
    ranked = sorted(scored.values(), key=lambda row: (row[0], row[1]), reverse=True)
    return [row[2] for row in ranked[:top_k]]


def _structured(events: list[dict]) -> list[dict]:
    latest: dict[tuple[str, str], dict] = {}
    work: dict[str, dict] = {}
    for event in events:
        meta = event.get("metadata", {})
        op = str(meta.get("op", ""))
        key = str(meta.get("key", ""))
        if not key:
            continue
        if op == "set_work":
            work[key] = event
        elif op in {"set_fact", "set_procedure", "set_capability"}:
            latest[(op, key)] = event
    rows = list(latest.values()) + list(work.values())
    return sorted(rows, key=lambda e: int(e.get("metadata", {}).get("sequence", 0)))


def build_condition_messages(events: list[dict], tasks: list[dict], stage: int, condition: str) -> list[dict[str, str]]:
    stage_tasks = tasks_for_stage(tasks, stage)
    if not stage_tasks:
        raise ValueError(f"no tasks for stage {stage}")
    visible = _visible(events, stage)
    if condition == "B0":
        evidence = []
        label = "NO PRIOR EXPERIENCE"
    elif condition == "B1":
        evidence = visible
        label = "FULL PUBLIC HISTORY"
    elif condition == "B2":
        evidence = _retrieved(visible, stage_tasks)
        label = "RETRIEVAL-ONLY PUBLIC EVIDENCE (no explicit supersession semantics)"
    elif condition == "B3":
        evidence = _structured(visible)
        label = "STRUCTURED CURRENT PUBLIC STATE (latest public state per semantic key)"
    else:
        raise ValueError(f"unknown condition {condition}")

    evidence_text = "\n".join(canonical_json(e) for e in evidence) if evidence else "(none)"
    task_payload = [{"task_key": t["task_key"], "prompt": t["prompt"]} for t in stage_tasks]
    user = (
        f"Condition: {condition}\nCognitive age: {stage}\n\n{label}:\n{evidence_text}\n\n"
        f"TASKS:\n{json.dumps(task_payload, ensure_ascii=False, indent=2)}\n\n"
        "For known answers include supporting source_ref(s) in the answer string. Return only JSON."
    )
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]
