from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

ALLOWED_FIELDS = {
    "source_experience",
    "new_task",
    "candidate_id",
    "transferred_pattern",
    "independent_reuse",
    "reuse_boundary",
    "controlled_variables",
    "changed_variable",
    "metrics_before",
    "metrics_after",
    "regressions",
    "evidence",
    "verdict",
}


def growth_inbox_path(data_root: Path | None = None) -> Path:
    root = Path(data_root or os.environ.get("AGENT_DATA_ROOT", "/home/ubuntu/agent-data"))
    return root / "growth-proof" / "inbox.jsonl"


def normalize_growth_context(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("growth_context_must_be_object")
    unknown = sorted(set(payload) - ALLOWED_FIELDS)
    if unknown:
        raise ValueError("growth_context_unknown_fields:" + ",".join(unknown))
    source = payload.get("source_experience")
    if not isinstance(source, list) or not [x for x in source if str(x).strip()]:
        raise ValueError("growth_context_source_experience_required")
    result = {k: v for k, v in payload.items() if k in ALLOWED_FIELDS}
    result["source_experience"] = [str(x).strip() for x in source if str(x).strip()]
    result["independent_reuse"] = bool(payload.get("independent_reuse"))
    return result


def emit_growth_observation(
    payload: dict[str, Any],
    *,
    data_root: Path | None = None,
) -> Path:
    observation = normalize_growth_context(payload)
    inbox = growth_inbox_path(data_root)
    inbox.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(observation, ensure_ascii=False, sort_keys=True) + "\n"
    with inbox.open("a", encoding="utf-8") as fh:
        fh.write(line)
        fh.flush()
        os.fsync(fh.fileno())
    return inbox
