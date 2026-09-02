from __future__ import annotations

import fcntl
import hashlib
import json
import os
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Event
from typing import Any, Mapping

from agent_core.core_supervisor import CoreSupervisorReconciler, ReconcileIntent
from agent_core.core_work_items import WorkItemStore
from agent_core.employee_lifecycle import EmployeeLifecycle


LEADER_SCHEMA = "agentos.core-supervisor-leader/v1"
STATE_SCHEMA = "agentos.core-supervisor-state/v1"
CYCLE_SCHEMA = "agentos.core-supervisor-cycle/v1"
INTENT_RECORD_SCHEMA = "agentos.core-reconcile-record/v1"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)


def _atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, sort_keys=True, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def _read(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("supervisor_state_invalid")
    return value


@dataclass(frozen=True, slots=True)
class SupervisorLeaderLease:
    schema: str
    owner_id: str
    generation: int
    claimed_at: str
    heartbeat_at: str
    expires_at: str
    prior_owner_state: str


@dataclass(frozen=True, slots=True)
class SupervisorCycleReceipt:
    schema: str
    cycle_generation: int
    owner_id: str
    leader_generation: int
    observed_at: str
    plan_digest: str
    new_intent_count: int
    total_planned_intent_count: int
    suppressed_count: int
    error_count: int
    blocked_assignment_count: int
    next_poll_seconds: int
    dispatch_performed: bool = False
    authority_boundary: str = "persistent_observe_plan_only"


class CoreSupervisorService:
    """Persistent Core loop that observes and journals work, but does not dispatch it.

    S3 deliberately stops before execution authority. It owns singleton process
    coordination, repeated reconciliation, durable intent journaling, cycle receipts,
    crash-safe restart state, and adaptive polling. S4 is responsible for handing a
    planned intent to governed ONE delivery.
    """

    def __init__(
        self,
        lifecycle: EmployeeLifecycle,
        *,
        owner_id: str,
        base_poll_seconds: int = 5,
        max_poll_seconds: int = 60,
    ) -> None:
        owner = str(owner_id or "").strip()
        if not owner or len(owner) > 180 or any(ch in owner for ch in "/\\\0"):
            raise ValueError("invalid_supervisor_owner_id")
        if base_poll_seconds < 1 or max_poll_seconds < base_poll_seconds:
            raise ValueError("invalid_supervisor_poll_interval")
        self.lifecycle = lifecycle
        self.runtime = lifecycle.runtime
        self.reconciler = CoreSupervisorReconciler(lifecycle)
        self.work_items = WorkItemStore(self.runtime)
        self.owner_id = owner
        self.base_poll_seconds = int(base_poll_seconds)
        self.max_poll_seconds = int(max_poll_seconds)
        self.root = self.runtime.root / "supervisor"
        self.leader_path = self.root / "leader.json"
        self.leader_lock_path = self.root / "leader.lock"
        self.state_path = self.root / "state.json"
        self.intents_dir = self.root / "intents"
        self.cycles_dir = self.root / "cycles"

    def _lock(self):
        self.leader_lock_path.parent.mkdir(parents=True, exist_ok=True)
        return self.leader_lock_path.open("a+", encoding="utf-8")

    def claim_leader(self, *, lease_seconds: int = 30, now: datetime | None = None) -> SupervisorLeaderLease:
        if lease_seconds < 5 or lease_seconds > 300:
            raise ValueError("supervisor_leader_lease_out_of_range")
        current = now or _now()
        with self._lock() as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                existing = _read(self.leader_path)
                generation = 1
                prior_state = "known"
                claimed_at = _iso(current)
                if existing:
                    if existing.get("schema") != LEADER_SCHEMA:
                        raise ValueError("supervisor_leader_state_invalid")
                    expires = _parse(str(existing.get("expires_at") or "1970-01-01T00:00:00Z"))
                    same_owner = existing.get("owner_id") == self.owner_id
                    if expires > current and not same_owner:
                        raise RuntimeError("supervisor_leader_already_active")
                    if same_owner and expires > current:
                        generation = int(existing.get("generation") or 1)
                        claimed_at = str(existing.get("claimed_at") or claimed_at)
                    else:
                        generation = int(existing.get("generation") or 0) + 1
                        prior_state = "unknown"
                lease = SupervisorLeaderLease(
                    schema=LEADER_SCHEMA,
                    owner_id=self.owner_id,
                    generation=generation,
                    claimed_at=claimed_at,
                    heartbeat_at=_iso(current),
                    expires_at=_iso(current + timedelta(seconds=lease_seconds)),
                    prior_owner_state=prior_state,
                )
                _atomic(self.leader_path, asdict(lease))
                return lease
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def heartbeat_leader(
        self,
        generation: int,
        *,
        lease_seconds: int = 30,
        now: datetime | None = None,
    ) -> SupervisorLeaderLease:
        current = now or _now()
        with self._lock() as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                raw = _read(self.leader_path)
                if not raw or raw.get("schema") != LEADER_SCHEMA:
                    raise RuntimeError("supervisor_leader_missing")
                if raw.get("owner_id") != self.owner_id or int(raw.get("generation") or 0) != int(generation):
                    raise PermissionError("supervisor_leader_not_owned")
                if _parse(str(raw.get("expires_at"))) <= current:
                    raise RuntimeError("supervisor_leader_expired")
                lease = SupervisorLeaderLease(
                    schema=LEADER_SCHEMA,
                    owner_id=self.owner_id,
                    generation=int(generation),
                    claimed_at=str(raw.get("claimed_at")),
                    heartbeat_at=_iso(current),
                    expires_at=_iso(current + timedelta(seconds=lease_seconds)),
                    prior_owner_state=str(raw.get("prior_owner_state") or "known"),
                )
                _atomic(self.leader_path, asdict(lease))
                return lease
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _require_leader(self, generation: int, *, now: datetime) -> SupervisorLeaderLease:
        raw = _read(self.leader_path)
        if not raw or raw.get("schema") != LEADER_SCHEMA:
            raise RuntimeError("supervisor_leader_missing")
        lease = SupervisorLeaderLease(**raw)
        if lease.owner_id != self.owner_id or lease.generation != int(generation):
            raise PermissionError("supervisor_leader_not_owned")
        if _parse(lease.expires_at) <= now:
            raise RuntimeError("supervisor_leader_expired")
        return lease

    def _persisted_reconcile_ids(self) -> set[str]:
        if not self.intents_dir.exists():
            return set()
        return {path.stem for path in self.intents_dir.glob("reconcile_*.json") if path.is_file()}

    def _persist_intent(self, intent: ReconcileIntent, *, cycle_generation: int, now: datetime) -> bool:
        path = self.intents_dir / f"{intent.reconcile_id}.json"
        if path.exists():
            return False
        _atomic(
            path,
            {
                "schema": INTENT_RECORD_SCHEMA,
                "reconcile_id": intent.reconcile_id,
                "state": "planned",
                "planned_at": _iso(now),
                "planned_by_cycle": cycle_generation,
                "intent": intent.as_dict(),
                "dispatch_performed": False,
            },
        )
        return True

    def _blocked_assignments(self, dependency_states: Mapping[str, str]) -> set[str]:
        result: set[str] = set()
        if not self.work_items.root.exists():
            return result
        for path in sorted(self.work_items.root.glob("*.json")):
            try:
                item = self.work_items.get(path.stem)
            except Exception:
                continue
            if item.state == "open" and item.dependency_refs and not self.work_items.dependencies_ready(item.work_item_id, dependency_states):
                result.add(item.assignment_id)
        return result

    def run_cycle(
        self,
        leader_generation: int,
        *,
        dependency_states: Mapping[str, str] | None = None,
        now: datetime | None = None,
    ) -> SupervisorCycleReceipt:
        current = now or _now()
        leader = self._require_leader(leader_generation, now=current)
        previous = _read(self.state_path) or {}
        cycle_generation = int(previous.get("cycle_generation") or 0) + 1
        blocked = self._blocked_assignments(dependency_states or {})
        persisted = self._persisted_reconcile_ids()
        plan = self.reconciler.reconcile(
            blocked_assignment_ids=blocked,
            persisted_reconcile_ids=persisted,
            now=current,
        )
        new_count = sum(
            1 for intent in plan.intents if self._persist_intent(intent, cycle_generation=cycle_generation, now=current)
        )
        plan_payload = plan.as_dict()
        plan_digest = hashlib.sha256(
            json.dumps(plan_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        previous_digest = str(previous.get("last_plan_digest") or "")
        previous_poll = int(previous.get("next_poll_seconds") or self.base_poll_seconds)
        if new_count > 0 or plan_digest != previous_digest:
            next_poll = self.base_poll_seconds
        else:
            next_poll = min(self.max_poll_seconds, max(self.base_poll_seconds, previous_poll * 2))
        total_planned = len(self._persisted_reconcile_ids())
        receipt = SupervisorCycleReceipt(
            schema=CYCLE_SCHEMA,
            cycle_generation=cycle_generation,
            owner_id=self.owner_id,
            leader_generation=leader.generation,
            observed_at=_iso(current),
            plan_digest=plan_digest,
            new_intent_count=new_count,
            total_planned_intent_count=total_planned,
            suppressed_count=len(plan.suppressed),
            error_count=len(plan.errors),
            blocked_assignment_count=len(blocked),
            next_poll_seconds=next_poll,
        )
        _atomic(self.cycles_dir / f"{cycle_generation:08d}.json", asdict(receipt))
        _atomic(
            self.state_path,
            {
                "schema": STATE_SCHEMA,
                "status": "running",
                "owner_id": self.owner_id,
                "leader_generation": leader.generation,
                "cycle_generation": cycle_generation,
                "last_cycle_at": receipt.observed_at,
                "last_plan_digest": plan_digest,
                "next_poll_seconds": next_poll,
                "planned_intent_count": total_planned,
                "last_cycle_receipt": f"cycles/{cycle_generation:08d}.json",
                "dispatch_performed": False,
            },
        )
        return receipt

    def health(self, *, now: datetime | None = None) -> dict[str, Any]:
        current = now or _now()
        state = _read(self.state_path) or {}
        leader = _read(self.leader_path) or {}
        leader_live = False
        if leader.get("schema") == LEADER_SCHEMA and leader.get("expires_at"):
            leader_live = _parse(str(leader["expires_at"])) > current
        return {
            "schema": "agentos.core-supervisor-health/v1",
            "status": "running" if leader_live and state.get("status") == "running" else "inactive",
            "leader_live": leader_live,
            "owner_id": state.get("owner_id"),
            "leader_generation": state.get("leader_generation"),
            "cycle_generation": int(state.get("cycle_generation") or 0),
            "last_cycle_at": state.get("last_cycle_at"),
            "next_poll_seconds": state.get("next_poll_seconds"),
            "planned_intent_count": int(state.get("planned_intent_count") or 0),
            "dispatch_performed": False,
        }

    def run_forever(
        self,
        *,
        stop_event: Event | None = None,
        leader_lease_seconds: int = 30,
    ) -> None:
        stopper = stop_event or Event()
        lease = self.claim_leader(lease_seconds=leader_lease_seconds)
        while not stopper.is_set():
            receipt = self.run_cycle(lease.generation)
            lease = self.heartbeat_leader(lease.generation, lease_seconds=leader_lease_seconds)
            stopper.wait(receipt.next_poll_seconds)
        # Exiting does not erase durable state or pretend pending intents are done.
