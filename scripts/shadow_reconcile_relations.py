#!/usr/bin/env python3
"""Run read-only Global Cognitive Reconciliation on a relation seed.

This CLI never writes ProjectState, memory, source repositories, or relation
seeds. It loads a shadow seed, optionally focuses on conversational aliases,
and emits machine-readable reconciliation issues for review/synthesis.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

# A checkout-local script must be runnable directly without depending on an
# editable install to expose the repo root. Keep this bootstrap local to the CLI;
# it does not change source authority or import behavior inside the packages.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from agent_core.cognitive_reconciliation import CognitiveReconciliationPlanner
from agent_core.relational_seed import load_relation_seed


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Shadow-reconcile AgentOS relational memory")
    parser.add_argument("seed", type=Path, help="agentos.relation-seed/v1 JSON file")
    parser.add_argument("--focus", action="append", default=[], help="entity id or alias to focus; repeatable")
    parser.add_argument("--trigger-ref", default="cli:shadow-reconcile-relations")
    parser.add_argument("--fail-on-issues", action="store_true", help="exit 3 when reconciliation issues exist")
    return parser


def _resolve_focus(graph, values: list[str]) -> tuple[str, ...] | None:
    if not values:
        return None
    resolved: list[str] = []
    for value in values:
        if graph.entity(value) is not None:
            resolved.append(value)
            continue
        matches = graph.resolve(value, limit=1)
        if not matches:
            raise ValueError(f"focus could not be resolved: {value}")
        resolved.append(matches[0].entity_id)
    return tuple(dict.fromkeys(resolved))


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        payload = json.loads(args.seed.read_text(encoding="utf-8"))
        loaded = load_relation_seed(payload)
        graph = loaded.build_graph()
        focus = _resolve_focus(graph, list(args.focus))
        plan = CognitiveReconciliationPlanner(graph).plan(
            trigger_ref=args.trigger_ref,
            focus_entity_ids=focus,
        )
    except (OSError, json.JSONDecodeError, ValueError, KeyError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2

    output = {
        "ok": True,
        "mode": loaded.mode,
        "trigger_ref": plan.trigger_ref,
        "entity_ids": list(plan.entity_ids),
        "relation_ids": list(plan.relation_ids),
        "requires_work": plan.requires_work,
        "issues": [
            {
                "kind": item.kind,
                "subject_ref": item.subject_ref,
                "related_ref": item.related_ref,
                "priority": item.priority,
                "reason": item.reason,
            }
            for item in plan.issues
        ],
    }
    print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    return 3 if args.fail_on_issues and plan.requires_work else 0


if __name__ == "__main__":
    raise SystemExit(main())
