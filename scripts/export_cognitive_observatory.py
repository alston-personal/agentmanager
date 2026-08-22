#!/usr/bin/env python3
"""Export a persisted Cognitive Observatory project timeline as JSON or DOT."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from agent_core.cognitive_observatory_export import export_timeline_dot, export_timeline_json
from agent_core.cognitive_observatory_store import CognitiveObservatoryStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, help="Path to the Cognitive Observatory SQLite database")
    parser.add_argument("--project", required=True, help="Project ID to export")
    parser.add_argument("--format", choices=("json", "dot"), default="json")
    parser.add_argument("--output", help="Optional output path; stdout when omitted")
    parser.add_argument("--title", default="AgentOS Cognitive Evolution", help="DOT graph title")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    db_path = Path(args.db)
    if not db_path.exists():
        print(f"observatory database not found: {db_path}", file=sys.stderr)
        return 2
    if not args.project.strip():
        print("project is required", file=sys.stderr)
        return 2

    store = CognitiveObservatoryStore(db_path)
    timeline = store.timeline(args.project)
    deltas = store.deltas(args.project)
    if args.format == "dot":
        content = export_timeline_dot(timeline, deltas, title=args.title)
    else:
        content = export_timeline_json(timeline, deltas)

    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(content, encoding="utf-8")
    else:
        sys.stdout.write(content)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
