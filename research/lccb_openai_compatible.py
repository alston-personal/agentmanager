"""Pure helpers for running frozen LCCB public packs on OpenAI-compatible APIs.

Network I/O and secrets stay outside this module. The helpers build one batch
prompt per cognitive age and parse task-keyed JSON responses without touching
evaluator-only labels.
"""

from __future__ import annotations

from hashlib import sha256
import json
from typing import Iterable, Mapping


SYSTEM_INSTRUCTION = (
    "You are participating in a longitudinal agent-memory benchmark. "
    "Use only the supplied public Project Meridian experience. "
    "Answer each task with the current state established by that history. "
    "If the history does not establish an answer, answer exactly 'unknown'. "
    "Do not invent facts. Return only one JSON object mapping every task_key to a concise string answer."
)


def canonical_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def context_for_stage(events: Iterable[dict], stage: int) -> tuple[dict, ...]:
    return tuple(item for item in events if int(item.get("metadata", {}).get("sequence", 0)) <= stage)


def tasks_for_stage(tasks: Iterable[dict], stage: int) -> tuple[dict, ...]:
    return tuple(sorted((item for item in tasks if int(item.get("stage", -1)) == stage), key=lambda item: item["task_key"]))


def build_batch_messages(events: Iterable[dict], tasks: Iterable[dict], stage: int) -> list[dict[str, str]]:
    visible = context_for_stage(events, stage)
    stage_tasks = tasks_for_stage(tasks, stage)
    if not stage_tasks:
        raise ValueError(f"no public tasks for stage {stage}")
    experience_text = "\n".join(canonical_json(item) for item in visible) if visible else "(no benchmark experience yet)"
    task_payload = [{"task_key": item["task_key"], "prompt": item["prompt"]} for item in stage_tasks]
    user = (
        f"Cognitive age: {stage}\n\n"
        "PUBLIC EXPERIENCE (ordered):\n"
        f"{experience_text}\n\n"
        "TASKS:\n"
        f"{json.dumps(task_payload, ensure_ascii=False, indent=2)}\n\n"
        "Return only JSON: {\"task_key\": \"answer\", ...}."
    )
    return [
        {"role": "system", "content": SYSTEM_INSTRUCTION},
        {"role": "user", "content": user},
    ]


def parse_task_answers(text: str, expected_task_keys: Iterable[str]) -> dict[str, str]:
    raw = text.strip()
    if raw.startswith("```"):
        lines = raw.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        raw = "\n".join(lines).strip()
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("model response is not valid JSON") from exc
    if not isinstance(value, dict):
        raise ValueError("model response must be a JSON object")
    expected = set(expected_task_keys)
    received = set(value)
    if received != expected:
        missing = sorted(expected - received)
        extra = sorted(received - expected)
        raise ValueError(f"task-key mismatch missing={missing} extra={extra}")
    answers = {str(key): str(answer).strip() for key, answer in value.items()}
    if any(not answer for answer in answers.values()):
        raise ValueError("empty task answer")
    return answers


def response_hash(answer: str) -> str:
    return sha256(answer.encode("utf-8")).hexdigest()


def prompt_hash(messages: list[dict[str, str]]) -> str:
    return sha256(canonical_json(messages).encode("utf-8")).hexdigest()
