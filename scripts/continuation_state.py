#!/usr/bin/env python3
"""Minimal continuation-state reconciler and regression self-test.

This module protects one narrow invariant: a compacted snapshot may never roll
back newer user intent. It is intentionally dependency-free so it can run in
CI, maintenance timers, or a weak executor bootstrap.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, asdict
import json
from typing import Iterable


@dataclass(frozen=True)
class UserEvent:
    seq: int
    kind: str
    text: str
    goal_revision: int | None = None


@dataclass
class ContinuationState:
    snapshot_revision: int
    snapshot_cutoff_seq: int
    active_goal_revision: int
    active_goal_text: str
    pending_user_events: list[dict]
    unresolved_items: list[str]


def reconcile(snapshot: ContinuationState, events: Iterable[UserEvent]) -> ContinuationState:
    """Replay only events newer than the snapshot cutoff, in sequence order."""
    tail = sorted((e for e in events if e.seq > snapshot.snapshot_cutoff_seq), key=lambda e: e.seq)
    state = ContinuationState(**asdict(snapshot))
    seen = []
    for event in tail:
        seen.append(asdict(event))
        if event.kind in {"goal", "goal_update", "correction"}:
            revision = event.goal_revision
            if revision is None:
                revision = state.active_goal_revision + 1
            if revision < state.active_goal_revision:
                raise ValueError("goal revision rollback detected")
            state.active_goal_revision = revision
            state.active_goal_text = event.text
        elif event.kind == "cancel_goal":
            revision = event.goal_revision or (state.active_goal_revision + 1)
            if revision < state.active_goal_revision:
                raise ValueError("goal revision rollback detected")
            state.active_goal_revision = revision
            state.active_goal_text = "[cancelled] " + event.text
        elif event.kind == "tool_result":
            # Tool results are evidence. They do not mutate user intent.
            pass
    state.pending_user_events = seen
    if tail:
        state.snapshot_revision += 1
    return state


def self_test() -> None:
    original = ContinuationState(
        snapshot_revision=7,
        snapshot_cutoff_seq=100,
        active_goal_revision=3,
        active_goal_text="Goal A: validate core parser",
        pending_user_events=[],
        unresolved_items=["publish web demo"],
    )
    events = [
        UserEvent(101, "goal", "Goal B: publish a usable web demo", 4),
        UserEvent(102, "tool_result", "Goal A validation passed"),
        UserEvent(103, "correction", "Goal B must be reachable from the official website", 5),
    ]
    state = reconcile(original, events)
    assert state.active_goal_revision == 5
    assert state.active_goal_text == "Goal B must be reachable from the official website"
    assert [e["seq"] for e in state.pending_user_events] == [101, 102, 103]

    try:
        reconcile(state, [UserEvent(104, "goal", "stale goal", 4)])
    except ValueError:
        pass
    else:
        raise AssertionError("revision rollback was not rejected")

    print("continuation_monotonicity=PASS")
    print("newer_goal_survives_old_tool_result=PASS")
    print("correction_replay=PASS")
    print("revision_rollback_rejected=PASS")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--self-test", action="store_true")
    p.add_argument("--snapshot")
    p.add_argument("--events")
    args = p.parse_args()
    if args.self_test:
        self_test()
        return 0
    if not args.snapshot or not args.events:
        p.error("use --self-test or provide --snapshot and --events")
    snapshot = ContinuationState(**json.load(open(args.snapshot, encoding="utf-8")))
    raw = json.load(open(args.events, encoding="utf-8"))
    result = reconcile(snapshot, [UserEvent(**e) for e in raw])
    print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
