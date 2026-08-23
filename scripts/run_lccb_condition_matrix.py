#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from research.lccb_condition_prompts import build_condition_messages
from research.lccb_openai_compatible import parse_task_answers, prompt_hash, response_hash, tasks_for_stage
from scripts.run_lccb_openai_compatible import _chat


def _load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--pack", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--conditions", default="B0,B1,B2,B3")
    p.add_argument("--stages", default="0,100,1000")
    p.add_argument("--temperature", type=float, default=0.0)
    p.add_argument("--repeat", type=int, default=3)
    p.add_argument("--max-tokens", type=int, default=1600)
    args = p.parse_args()

    base_url = os.environ.get("LCCB_BASE_URL", "").strip()
    api_key = os.environ.get("LCCB_API_KEY", "").strip()
    model = os.environ.get("LCCB_MODEL", "").strip()
    if not base_url or not api_key or not model:
        print("LCCB_BASE_URL, LCCB_API_KEY and LCCB_MODEL are required", file=sys.stderr)
        return 2

    root = Path(args.pack)
    events = _load_jsonl(root / "public" / "experience.jsonl")
    tasks = _load_jsonl(root / "public" / "tasks.jsonl")
    conditions = tuple(x.strip() for x in args.conditions.split(",") if x.strip())
    stages = tuple(int(x.strip()) for x in args.stages.split(",") if x.strip())
    rows: list[dict] = []
    for repeat in range(args.repeat):
        for condition in conditions:
            for stage in stages:
                stage_tasks = tasks_for_stage(tasks, stage)
                messages = build_condition_messages(events, tasks, stage, condition)
                started = _utc_now()
                raw = _chat(base_url, api_key, model, messages, temperature=args.temperature, max_tokens=args.max_tokens)
                completed = _utc_now()
                answers = parse_task_answers(raw, (item["task_key"] for item in stage_tasks))
                p_hash = prompt_hash(messages)
                for item in stage_tasks:
                    answer = answers[item["task_key"]]
                    rows.append({
                        "schema_version": "agentos.lccb-condition-response/v1",
                        "condition": condition,
                        "stage": stage,
                        "repeat": repeat,
                        "task_key": item["task_key"],
                        "provider_family": "openai-compatible",
                        "model": model,
                        "temperature": args.temperature,
                        "max_tokens": args.max_tokens,
                        "prompt_hash": p_hash,
                        "response_hash": response_hash(answer),
                        "response_text": answer,
                        "started_at": started,
                        "completed_at": completed,
                    })
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(json.dumps(r, ensure_ascii=False, sort_keys=True) for r in rows) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
