#!/usr/bin/env python3
"""Run frozen public LCCB stages against an OpenAI-compatible chat endpoint.

Required environment variables:
  LCCB_BASE_URL   e.g. https://example/v1
  LCCB_API_KEY    bearer token (never written to output)
  LCCB_MODEL      immutable model/version identifier used for this series

The runner reads only public/ artifacts. Evaluator-only private labels are never
opened. One batched model call is made per requested cognitive age.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import urllib.error
import urllib.request

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from research.lccb_openai_compatible import (
    build_batch_messages,
    parse_task_answers,
    prompt_hash,
    response_hash,
    tasks_for_stage,
)


_PROVIDER_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AgentOS/1.0"


def _load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _chat(base_url: str, api_key: str, model: str, messages: list[dict[str, str]], *, temperature: float, max_tokens: int) -> str:
    url = base_url.rstrip("/") + "/chat/completions"
    body = json.dumps(
        {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            # Keep the same upstream HTTP contract as agent_core.ai_client.
            # Some compatible gateways/WAFs reject urllib's default Python UA.
            "User-Agent": _PROVIDER_USER_AGENT,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"provider HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"provider request failed: {type(exc).__name__}") from exc
    try:
        return str(payload["choices"][0]["message"]["content"])
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("provider response missing choices[0].message.content") from exc


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--pack", required=True, help="Frozen LCCB pack directory")
    p.add_argument("--output", required=True, help="Output JSONL for raw task responses")
    p.add_argument("--stages", default="0,100,1000")
    p.add_argument("--temperature", type=float, default=0.0)
    p.add_argument("--max-tokens", type=int, default=1200)
    p.add_argument("--repeat", type=int, default=1)
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    base_url = os.environ.get("LCCB_BASE_URL", "").strip()
    api_key = os.environ.get("LCCB_API_KEY", "").strip()
    model = os.environ.get("LCCB_MODEL", "").strip()
    if not base_url or not api_key or not model:
        print("LCCB_BASE_URL, LCCB_API_KEY and LCCB_MODEL are required", file=sys.stderr)
        return 2
    if args.repeat < 1:
        print("--repeat must be >= 1", file=sys.stderr)
        return 2

    root = Path(args.pack)
    experience_path = root / "public" / "experience.jsonl"
    tasks_path = root / "public" / "tasks.jsonl"
    private_path = root / "private" / "labels.jsonl"
    if not experience_path.exists() or not tasks_path.exists():
        print("frozen pack public artifacts are missing", file=sys.stderr)
        return 2
    # Explicitly do not read private_path; its existence is irrelevant to execution.
    _ = private_path

    events = _load_jsonl(experience_path)
    tasks = _load_jsonl(tasks_path)
    stages = tuple(int(value.strip()) for value in args.stages.split(",") if value.strip())
    rows: list[dict] = []

    for repeat in range(args.repeat):
        for stage in stages:
            stage_tasks = tasks_for_stage(tasks, stage)
            messages = build_batch_messages(events, tasks, stage)
            started = _utc_now()
            raw = _chat(
                base_url,
                api_key,
                model,
                messages,
                temperature=args.temperature,
                max_tokens=args.max_tokens,
            )
            completed = _utc_now()
            answers = parse_task_answers(raw, (item["task_key"] for item in stage_tasks))
            p_hash = prompt_hash(messages)
            for item in stage_tasks:
                answer = answers[item["task_key"]]
                rows.append(
                    {
                        "schema_version": "agentos.lccb-raw-response/v1",
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
                    }
                )

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
