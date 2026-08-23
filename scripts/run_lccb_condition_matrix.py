#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import time

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


def _chat_with_bounded_429_retry(
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
    *,
    temperature: float,
    max_tokens: int,
    retry_429: int,
    retry_delay_seconds: float,
    trace_label: str,
) -> str:
    retry_index = 0
    while True:
        try:
            return _chat(base_url, api_key, model, messages, temperature=temperature, max_tokens=max_tokens)
        except RuntimeError as exc:
            if str(exc) != "provider HTTP 429" or retry_index >= retry_429:
                raise
            delay = retry_delay_seconds * (2 ** retry_index)
            retry_index += 1
            print(
                f"LCCB provider 429 for {trace_label}; retry {retry_index}/{retry_429} after {delay:.1f}s",
                file=sys.stderr,
                flush=True,
            )
            time.sleep(delay)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--pack", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--conditions", default="B0,B1,B2,B3")
    p.add_argument("--stages", default="0,100,1000")
    p.add_argument("--temperature", type=float, default=0.0)
    p.add_argument("--repeat", type=int, default=3)
    p.add_argument("--max-tokens", type=int, default=1600)
    p.add_argument("--retry-429", type=int, default=0, help="Bounded retries for provider HTTP 429 only")
    p.add_argument("--retry-delay-seconds", type=float, default=20.0, help="Initial 429 backoff; doubles per retry")
    p.add_argument("--inter-call-delay-seconds", type=float, default=0.0, help="Optional pacing between successful provider calls")
    args = p.parse_args()

    if args.repeat < 1 or args.retry_429 < 0 or args.retry_delay_seconds < 0 or args.inter_call_delay_seconds < 0:
        print("invalid repeat/retry/delay arguments", file=sys.stderr)
        return 2

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
    call_index = 0
    for repeat in range(args.repeat):
        for condition in conditions:
            for stage in stages:
                stage_tasks = tasks_for_stage(tasks, stage)
                messages = build_condition_messages(events, tasks, stage, condition)
                prompt_characters = sum(len(message["content"]) for message in messages)
                prompt_utf8_bytes = sum(len(message["content"].encode("utf-8")) for message in messages)
                trace_label = f"repeat={repeat} condition={condition} stage={stage} prompt_chars={prompt_characters}"
                print(f"LCCB call start {trace_label}", file=sys.stderr, flush=True)
                started = _utc_now()
                raw = _chat_with_bounded_429_retry(
                    base_url,
                    api_key,
                    model,
                    messages,
                    temperature=args.temperature,
                    max_tokens=args.max_tokens,
                    retry_429=args.retry_429,
                    retry_delay_seconds=args.retry_delay_seconds,
                    trace_label=trace_label,
                )
                completed = _utc_now()
                print(f"LCCB call success {trace_label}", file=sys.stderr, flush=True)
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
                        "prompt_characters": prompt_characters,
                        "prompt_utf8_bytes": prompt_utf8_bytes,
                        "response_hash": response_hash(answer),
                        "response_text": answer,
                        "started_at": started,
                        "completed_at": completed,
                    })
                call_index += 1
                if args.inter_call_delay_seconds > 0 and call_index < args.repeat * len(conditions) * len(stages):
                    time.sleep(args.inter_call_delay_seconds)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(json.dumps(r, ensure_ascii=False, sort_keys=True) for r in rows) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
