#!/usr/bin/env python3
"""Convert exported GitHub snapshots into AgentOS ExperienceEvent JSONL.

Read-only shadow tool. Authentication/data fetching belongs to an external
GitHub connector/gh/MCP process. This script receives already-fetched JSON and
never accepts or stores GitHub credentials.

Input JSONL records use:
  {"type":"pull_request","data":{...}}
  {"type":"commit","data":{...}}
  {"type":"workflow_run","data":{...}}
  {"type":"record","data":{"kind":..., ...}}

Output is one ExperienceEvent JSON object per line.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Mapping

from agent_core.source_adapters.github import (
    GitHubExperienceAdapter,
    GitHubRecord,
    record_from_commit_snapshot,
    record_from_pr_snapshot,
    record_from_workflow_summary,
)


def _record(value: Mapping[str, Any]) -> GitHubRecord:
    record_type = str(value.get("type") or "").strip()
    data = value.get("data")
    if not isinstance(data, Mapping):
        raise ValueError("input record requires object field 'data'")
    if record_type == "pull_request":
        return record_from_pr_snapshot(data)
    if record_type == "commit":
        return record_from_commit_snapshot(data)
    if record_type == "workflow_run":
        return record_from_workflow_summary(data)
    if record_type == "record":
        return GitHubRecord(
            kind=str(data.get("kind") or ""),
            id=str(data.get("id") or ""),
            occurred_at=str(data.get("occurred_at") or ""),
            actor=str(data.get("actor") or ""),
            content=str(data.get("content") or ""),
            url=str(data.get("url") or "") or None,
            conversation_ref=str(data.get("conversation_ref") or "") or None,
            metadata=data.get("metadata") if isinstance(data.get("metadata"), Mapping) else {},
        )
    raise ValueError(f"unsupported input type: {record_type}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="GitHub -> AgentOS shadow ExperienceEvent JSONL")
    parser.add_argument("--project", required=True)
    parser.add_argument("--repository", required=True, help="owner/name")
    args = parser.parse_args(argv)

    records: list[GitHubRecord] = []
    for line_number, raw in enumerate(sys.stdin, start=1):
        raw = raw.strip()
        if not raw:
            continue
        try:
            value = json.loads(raw)
            if not isinstance(value, Mapping):
                raise ValueError("JSONL row must be an object")
            records.append(_record(value))
        except Exception as exc:
            print(f"line {line_number}: {exc}", file=sys.stderr)
            return 2

    def fetcher(position: str | None, limit: int):
        start = int(position or 0)
        page = records[start : start + limit]
        next_position = str(start + len(page)) if start + len(page) < len(records) else None
        return page, next_position

    adapter = GitHubExperienceAdapter(args.repository, fetcher)
    cursor = None
    while True:
        page = adapter.fetch_page(args.project, cursor, limit=50)
        for event in page.batch.events:
            print(json.dumps(event.to_dict(), ensure_ascii=False, sort_keys=True))
        if not page.has_more:
            break
        cursor = page.next_cursor
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
