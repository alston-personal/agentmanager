"""Public task projection for the controlled LCCB pack.

This projection deliberately excludes expected facts, forbidden facts, and
private evidence labels so model runners never need to open evaluator artifacts.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
import json
from typing import Iterable

from research.lccb_synthetic import HiddenLabel


@dataclass(frozen=True)
class PublicTask:
    task_key: str
    category: str
    stage: int
    prompt: str


def public_tasks(labels: Iterable[HiddenLabel]) -> tuple[PublicTask, ...]:
    return tuple(
        PublicTask(
            task_key=item.task_key,
            category=item.category,
            stage=item.stage,
            prompt=item.prompt,
        )
        for item in sorted(labels, key=lambda item: (item.stage, item.task_key))
    )


def public_tasks_jsonl(labels: Iterable[HiddenLabel]) -> str:
    rows = [json.dumps(asdict(item), ensure_ascii=False, sort_keys=True, separators=(",", ":")) for item in public_tasks(labels)]
    return "\n".join(rows) + "\n"
