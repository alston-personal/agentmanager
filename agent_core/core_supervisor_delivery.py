from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from agent_core.core_supervisor import RECONCILE_INTENT_SCHEMA
from agent_core.core_supervisor_service import INTENT_RECORD_SCHEMA, CoreSupervisorService
from agent_core.employee_wake import EmployeeWakeIntent, WAKE_INTENT_SCHEMA
from agent_core.employee_wake_delivery import EmployeeWakeDelivery
from agent_core.employee_presence import WAKE_CAPABILITY
from agent_core.transport_routing import RouteDecision, resolve_transport


DELIVERY_POLICY_SCHEMA = "agentos.core-supervisor-delivery-policy/v1"
DELIVERY_STATE_SCHEMA = "agentos.core-supervisor-delivery-state/v1"
DELIVERY_SUMMARY_SCHEMA = "agentos.core-supervisor-delivery-summary/v1"
DEFAULT_POLICY_PATH = Path(__file__).resolve().parent.parent / "governance" / "core-supervisor-delivery.json"
TERMINAL_ASSIGNMENT_STATES = {"completed", "cancelled", "blocked", "handoff"}
TERMINAL_DELIVERY_STATES = {"claimed", "terminal_observed", "superseded"}
RETRYABLE_DELIVERY_STATES = {"blocked", "unknown", "failed", "awaiting_claim"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_id(value: Any) -> str:
    text = str(value or "").strip()
    if not text or len(text) > 256 or any(ch in text for ch in "/\\\0") or text in {".", ".."}:
        raise ValueError("unsafe_supervisor_delivery_id")
    return text


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
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("supervisor_delivery_state_invalid")
    return payload


def _string_tuple(value: Any, *, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"invalid_persisted_wake_{field}")
    return tuple(value)


def _wake_from_dict(payload: Any) -> EmployeeWakeIntent:
    if not isinstance(payload, dict) or payload.get("schema") != WAKE_INTENT_SCHEMA:
        raise ValueError("invalid_persisted_wake_intent")
    if payload.get("credential_exposed") is not False:
        raise ValueError("invalid_persisted_wake_credential_boundary")
    return EmployeeWakeIntent(
        schema=WAKE_INTENT_SCHEMA,
        wake_id=_safe_id(payload.get("wake_id")),
        employee_id=_safe_id(payload.get("employee_id")),
        assignment_id=_safe_id(payload.get("assignment_id")),
        mode=str(payload.get("mode") or ""),
        expected_lease_generation=int(payload.get("expected_lease_generation") or 0),
        goal=str(payload.get("goal") or ""),
        thread_head=str(payload.get("thread_head") or ""),
        constraints=_string_tuple(payload.get("constraints"), field="constraints"),
        role_ids=_string_tuple(payload.get("role_ids"), field="role_ids"),
        skill_ids=_string_tuple(payload.get("skill_ids"), field="skill_ids"),
        resume_required=payload.get("resume_required") is True,
        prior_execution_state=str(payload.get("prior_execution_state") or ""),
        authority_boundary=str(payload.get("authority_boundary") or ""),
        executor_selection=str(payload.get("executor_selection") or ""),
        transport_selection=str(payload.get("transport_selection") or ""),
        credential_exposed=False,
    )


@dataclass(frozen=True, slots=True)
class WakeAuthorityDecision:
    policy_id: str
    reconcile_kind: str
    capability: str
    intent_class: str
    transport: str
    transport_authority: str
    transport_policy_id: str


class SupervisorWakeAuthorityResolver:
    """Resolve authority before looking at Node capability availability.

    The supervisor policy authorizes one bounded capability and delegates carrier
    choice to the existing authority-driven transport-routing policy. A reachable
    Node or workflow runner can never expand this policy.
    """

    def __init__(self, policy_path: str | Path = DEFAULT_POLICY_PATH, *, requested_transport: str = "one_direct") -> None:
        self.policy_path = Path(policy_path)
        self.requested_transport = str(requested_transport or "").strip()
        payload = json.loads(self.policy_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or payload.get("schema") != DELIVERY_POLICY_SCHEMA:
            raise ValueError("invalid_supervisor_delivery_policy")
        self.policy = payload

    def resolve(self, reconcile_intent: Mapping[str, Any], available_transports: Iterable[str] | Mapping[str, bool]) -> WakeAuthorityDecision:
        if reconcile_intent.get("schema") != RECONCILE_INTENT_SCHEMA:
            raise PermissionError("supervisor_delivery_reconcile_schema_rejected")
        kind = str(reconcile_intent.get("kind") or "")
        rule = self.policy.get("reconcile_kinds", {}).get(kind)
        if not isinstance(rule, dict):
            raise PermissionError("supervisor_delivery_kind_not_authorized")
        if reconcile_intent.get("authority_boundary") != "observe_and_select_only":
            raise PermissionError("supervisor_delivery_authority_boundary_rejected")
        for key in ("node_selection", "executor_selection", "transport_selection", "capability_authority"):
            if reconcile_intent.get(key) != "unbound":
                raise PermissionError("supervisor_delivery_prebound_authority_rejected")
        if reconcile_intent.get("credential_exposed") is not False:
            raise PermissionError("supervisor_delivery_credential_boundary_rejected")

        capability = str(rule.get("capability") or "")
        if capability != WAKE_CAPABILITY:
            raise PermissionError("supervisor_delivery_capability_not_authorized")
        intent_class = str(rule.get("intent_class") or "")
        route: RouteDecision = resolve_transport(
            intent_class,
            available_transports,
            requested_transport=self.requested_transport,
        )
        allowed = {str(item) for item in (rule.get("allowed_transports") or [])}
        if route.transport not in allowed:
            raise PermissionError("supervisor_delivery_transport_not_authorized")
        return WakeAuthorityDecision(
            policy_id=str(self.policy.get("policy_id") or "unknown"),
            reconcile_kind=kind,
            capability=capability,
            intent_class=intent_class,
            transport=route.transport,
            transport_authority=route.authority,
            transport_policy_id=route.policy_id,
        )


@dataclass(slots=True)
class SupervisorDeliveryState:
    schema: str
    reconcile_id: str
    employee_id: str
    assignment_id: str
    wake_id: str
    status: str
    created_at: str
    updated_at: str
    authority_policy_id: str
    transport_policy_id: str
    transport: str
    transport_authority: str
    capability: str
    supervisor_leader_generation: int
    dispatch_performed: bool = False
    presence_id: str | None = None
    presence_generation: int | None = None
    node_id: str | None = None
    wake_attempt_id: str | None = None
    task_id: str | None = None
    error_code: str | None = None


@dataclass(frozen=True, slots=True)
class SupervisorDeliverySummary:
    schema: str
    examined_count: int
    dispatch_count: int
    queued_count: int
    awaiting_claim_count: int
    claimed_count: int
    blocked_count: int
    unknown_count: int
    failed_count: int
    superseded_count: int
    error_count: int

    @property
    def dispatch_performed(self) -> bool:
        return self.dispatch_count > 0


class SupervisorWakeCoordinator:
    """Advance immutable Supervisor reconcile intents across governed ONE wake delivery.

    S3 reconcile records remain immutable evidence. S4 writes a separate delivery
    ledger. A Node accepting a wake capsule is not treated as assignment ownership:
    the coordinator continues in `awaiting_claim` until an Employee lease with the
    expected generation is observed.
    """

    def __init__(
        self,
        service: CoreSupervisorService,
        delivery: EmployeeWakeDelivery,
        authority: SupervisorWakeAuthorityResolver,
        *,
        available_transports: Iterable[str] | Mapping[str, bool],
        max_intents_per_cycle: int = 16,
    ) -> None:
        if max_intents_per_cycle < 1 or max_intents_per_cycle > 256:
            raise ValueError("invalid_supervisor_delivery_cycle_limit")
        self.service = service
        self.delivery = delivery
        self.authority = authority
        self.available_transports = available_transports
        self.max_intents_per_cycle = int(max_intents_per_cycle)
        self.root = service.root / "deliveries"

    def _path(self, reconcile_id: str) -> Path:
        return self.root / f"{_safe_id(reconcile_id)}.json"

    def get(self, reconcile_id: str) -> SupervisorDeliveryState | None:
        payload = _read(self._path(reconcile_id))
        if payload is None:
            return None
        if payload.get("schema") != DELIVERY_STATE_SCHEMA or payload.get("reconcile_id") != reconcile_id:
            raise ValueError("supervisor_delivery_state_invalid")
        return SupervisorDeliveryState(**payload)

    def _persist(self, state: SupervisorDeliveryState) -> SupervisorDeliveryState:
        _atomic(self._path(state.reconcile_id), asdict(state))
        return state

    def _load_reconcile(self, reconcile_id: str) -> tuple[dict[str, Any], EmployeeWakeIntent]:
        path = self.service.intents_dir / f"{_safe_id(reconcile_id)}.json"
        payload = _read(path)
        if payload is None:
            raise FileNotFoundError(reconcile_id)
        if payload.get("schema") != INTENT_RECORD_SCHEMA or payload.get("reconcile_id") != reconcile_id:
            raise ValueError("supervisor_reconcile_record_invalid")
        if payload.get("state") != "planned" or payload.get("dispatch_performed") is not False:
            raise PermissionError("supervisor_reconcile_record_not_delivery_eligible")
        intent = payload.get("intent")
        if not isinstance(intent, dict):
            raise ValueError("supervisor_reconcile_intent_missing")
        wake = _wake_from_dict(intent.get("wake_intent"))
        if intent.get("employee_id") != wake.employee_id or intent.get("assignment_id") != wake.assignment_id:
            raise ValueError("supervisor_reconcile_wake_identity_mismatch")
        return intent, wake

    def _current_exact_wake(self, wake: EmployeeWakeIntent, *, now: datetime) -> bool:
        current = self.service.reconciler.wake_planner.plan_next(wake.employee_id, now=now)
        return current is not None and current.as_dict() == wake.as_dict()

    def _claimed_or_terminal(self, state: SupervisorDeliveryState, wake: EmployeeWakeIntent, *, now: datetime) -> SupervisorDeliveryState | None:
        assignment = self.service.runtime.get_assignment(wake.assignment_id)
        if assignment.state in TERMINAL_ASSIGNMENT_STATES:
            state.status = "terminal_observed"
            state.error_code = None
            state.updated_at = _iso(now)
            return self._persist(state)
        lease = self.service.lifecycle.get_lease(wake.assignment_id)
        if (
            lease is not None
            and lease.status == "active"
            and lease.generation >= wake.expected_lease_generation
            and not self.service.lifecycle.lease_expired(lease, now=now)
        ):
            state.status = "claimed"
            state.error_code = None
            state.updated_at = _iso(now)
            return self._persist(state)
        return None

    def _new_state(self, reconcile_id: str, wake: EmployeeWakeIntent, decision: WakeAuthorityDecision, leader_generation: int, *, now: datetime, status: str, error_code: str | None = None) -> SupervisorDeliveryState:
        timestamp = _iso(now)
        return SupervisorDeliveryState(
            schema=DELIVERY_STATE_SCHEMA,
            reconcile_id=reconcile_id,
            employee_id=wake.employee_id,
            assignment_id=wake.assignment_id,
            wake_id=wake.wake_id,
            status=status,
            created_at=timestamp,
            updated_at=timestamp,
            authority_policy_id=decision.policy_id,
            transport_policy_id=decision.transport_policy_id,
            transport=decision.transport,
            transport_authority=decision.transport_authority,
            capability=decision.capability,
            supervisor_leader_generation=int(leader_generation),
            error_code=error_code,
        )

    @staticmethod
    def _copy_delivery(state: SupervisorDeliveryState, delivered: Any, *, now: datetime, status: str) -> SupervisorDeliveryState:
        state.status = status
        state.updated_at = _iso(now)
        state.dispatch_performed = state.dispatch_performed or bool(delivered.controller_entered) or delivered.status == "unknown"
        state.presence_id = delivered.presence_id
        state.presence_generation = delivered.presence_generation
        state.node_id = delivered.node_id
        state.wake_attempt_id = delivered.attempt_id
        state.task_id = delivered.task_id
        state.error_code = delivered.error_code
        return state

    def advance_one(self, reconcile_id: str, leader_generation: int, *, now: datetime | None = None) -> SupervisorDeliveryState:
        current_time = now or _now()
        self.service.require_leader(leader_generation, now=current_time)
        intent, wake = self._load_reconcile(reconcile_id)

        try:
            decision = self.authority.resolve(intent, self.available_transports)
        except Exception:
            existing = self.get(reconcile_id)
            if existing is not None:
                existing.status = "blocked"
                existing.error_code = "wake_authority_unavailable"
                existing.updated_at = _iso(current_time)
                return self._persist(existing)
            # Keep the authority rejection in a separate ledger without inventing
            # transport/capability data that was not successfully resolved.
            timestamp = _iso(current_time)
            return self._persist(SupervisorDeliveryState(
                schema=DELIVERY_STATE_SCHEMA,
                reconcile_id=reconcile_id,
                employee_id=wake.employee_id,
                assignment_id=wake.assignment_id,
                wake_id=wake.wake_id,
                status="blocked",
                created_at=timestamp,
                updated_at=timestamp,
                authority_policy_id="unresolved",
                transport_policy_id="unresolved",
                transport="unresolved",
                transport_authority="unresolved",
                capability=WAKE_CAPABILITY,
                supervisor_leader_generation=int(leader_generation),
                error_code="wake_authority_unavailable",
            ))

        state = self.get(reconcile_id)
        if state is None:
            state = self._new_state(reconcile_id, wake, decision, leader_generation, now=current_time, status="ready")
        if state.status in TERMINAL_DELIVERY_STATES:
            return state

        progressed = self._claimed_or_terminal(state, wake, now=current_time)
        if progressed is not None:
            return progressed

        if state.status == "queued":
            delivered = self.delivery.reconcile(wake.wake_id, int(state.presence_generation or 0), now=current_time)
            if delivered.status == "delivered":
                return self._persist(self._copy_delivery(state, delivered, now=current_time, status="awaiting_claim"))
            if delivered.status in {"unknown", "failed"}:
                return self._persist(self._copy_delivery(state, delivered, now=current_time, status=delivered.status))
            return state

        if state.status == "awaiting_claim":
            try:
                route = self.delivery.presence.resolve(wake.employee_id, now=current_time)
            except Exception:
                return state
            if state.presence_generation is None or route.generation <= state.presence_generation:
                return state
            # Employee moved after the previous Node accepted the wake but before
            # any assignment claim. The exact same wake may follow the new presence.

        if state.status in {"unknown", "failed"}:
            try:
                route = self.delivery.presence.resolve(wake.employee_id, now=current_time)
            except Exception:
                return state
            if state.presence_generation is not None and route.generation <= state.presence_generation:
                return state

        try:
            current_exact = self._current_exact_wake(wake, now=current_time)
        except Exception:
            state.status = "blocked"
            state.error_code = "current_wake_validation_failed"
            state.updated_at = _iso(current_time)
            return self._persist(state)
        if not current_exact:
            state.status = "superseded"
            state.error_code = "persisted_wake_no_longer_current"
            state.updated_at = _iso(current_time)
            return self._persist(state)

        try:
            delivered = self.delivery.deliver_intent(wake, now=current_time)
        except (KeyError, PermissionError, RuntimeError):
            state.status = "blocked"
            state.error_code = "employee_presence_unavailable"
            state.updated_at = _iso(current_time)
            return self._persist(state)
        except Exception:
            state.status = "blocked"
            state.error_code = "wake_delivery_pre_dispatch_failed"
            state.updated_at = _iso(current_time)
            return self._persist(state)

        mapped = delivered.status if delivered.status in {"queued", "unknown", "failed"} else "blocked"
        state = self._copy_delivery(state, delivered, now=current_time, status=mapped)
        if mapped == "blocked" and state.error_code is None:
            state.error_code = "wake_delivery_state_unexpected"
        return self._persist(state)

    def advance_all(self, leader_generation: int, *, now: datetime | None = None) -> SupervisorDeliverySummary:
        current_time = now or _now()
        self.service.require_leader(leader_generation, now=current_time)
        candidates: list[str] = []
        if self.service.intents_dir.exists():
            for path in sorted(self.service.intents_dir.glob("reconcile_*.json")):
                reconcile_id = path.stem
                existing = self.get(reconcile_id)
                if existing is not None and existing.status in TERMINAL_DELIVERY_STATES:
                    continue
                candidates.append(reconcile_id)
                if len(candidates) >= self.max_intents_per_cycle:
                    break

        counts = {
            "dispatch": 0,
            "queued": 0,
            "awaiting_claim": 0,
            "claimed": 0,
            "blocked": 0,
            "unknown": 0,
            "failed": 0,
            "superseded": 0,
            "error": 0,
        }
        for reconcile_id in candidates:
            before = self.get(reconcile_id)
            before_attempt = before.wake_attempt_id if before else None
            try:
                state = self.advance_one(reconcile_id, leader_generation, now=current_time)
            except Exception:
                counts["error"] += 1
                continue
            if state.dispatch_performed and state.wake_attempt_id and state.wake_attempt_id != before_attempt:
                counts["dispatch"] += 1
            if state.status in counts:
                counts[state.status] += 1

        return SupervisorDeliverySummary(
            schema=DELIVERY_SUMMARY_SCHEMA,
            examined_count=len(candidates),
            dispatch_count=counts["dispatch"],
            queued_count=counts["queued"],
            awaiting_claim_count=counts["awaiting_claim"],
            claimed_count=counts["claimed"],
            blocked_count=counts["blocked"],
            unknown_count=counts["unknown"],
            failed_count=counts["failed"],
            superseded_count=counts["superseded"],
            error_count=counts["error"],
        )

    def health(self) -> dict[str, Any]:
        counts: dict[str, int] = {}
        if self.root.exists():
            for path in self.root.glob("reconcile_*.json"):
                payload = _read(path) or {}
                status = str(payload.get("status") or "invalid")
                counts[status] = counts.get(status, 0) + 1
        return {
            "schema": "agentos.core-supervisor-delivery-health/v1",
            "policy_id": str(self.authority.policy.get("policy_id") or "unknown"),
            "requested_transport": self.authority.requested_transport,
            "states": dict(sorted(counts.items())),
        }
