"""Auditable SideEffect Ledger for governed external actions.

The ledger is executor-neutral. It records intent/effect lineage and enforces an
idempotent prepare -> commit|fail -> compensate lifecycle. It never accepts a
raw model/runtime decision as authority; preparation requires an intent-bound
ActionAuthorization from the Governance Kernel.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha256
import json
from typing import Any

from agent_core.action_authorization import ActionAuthorization
from agent_core.governance import CapabilityLevel
from runtime_core.governance_v1 import ActionIntent


SIDE_EFFECT_STATUSES = frozenset({"prepared", "committed", "failed", "compensated"})


def _hash(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
    return sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SideEffectRecord:
    side_effect_id: str
    intent_id: str
    work_id: str | None
    kind: str
    target: str
    intent_hash: str
    status: str
    idempotency_key: str
    authorization_reason: str
    compensation_ref: str | None = None
    receipt_ref: str | None = None
    failure_reason: str | None = None

    def __post_init__(self) -> None:
        if self.status not in SIDE_EFFECT_STATUSES:
            raise ValueError("invalid side-effect status")
        if not self.side_effect_id.strip() or not self.intent_id.strip() or not self.kind.strip() or not self.target.strip():
            raise ValueError("side-effect identity fields are required")
        if not self.idempotency_key.strip() or not self.intent_hash.strip() or not self.authorization_reason.strip():
            raise ValueError("idempotency/intent hash/authorization reason are required")
        if self.status == "committed" and not self.receipt_ref:
            raise ValueError("committed side effect requires receipt")
        if self.status == "failed" and not self.failure_reason:
            raise ValueError("failed side effect requires reason")
        if self.status == "compensated" and (not self.compensation_ref or not self.receipt_ref):
            raise ValueError("compensated side effect requires compensation and receipt")


class InMemorySideEffectLedger:
    def __init__(self) -> None:
        self._records: dict[str, SideEffectRecord] = {}
        self._by_idempotency: dict[str, str] = {}

    def prepare(
        self,
        *,
        intent: ActionIntent,
        authorization: ActionAuthorization,
        kind: str,
        target: str,
        work_id: str | None = None,
        compensation_ref: str | None = None,
    ) -> SideEffectRecord:
        if authorization.intent_id != intent.intent_id or authorization.capability != intent.capability:
            raise ValueError("authorization does not bind this intent")
        if not authorization.allowed or authorization.effective_level < CapabilityLevel.ACT:
            raise PermissionError("external side effect requires governed ACT-or-higher authorization")

        existing_id = self._by_idempotency.get(intent.idempotency_key)
        if existing_id:
            existing = self._records[existing_id]
            expected = _hash(intent.__dict__)
            if existing.intent_hash != expected:
                raise ValueError("idempotency key reused for different intent")
            return existing

        intent_hash = _hash(intent.__dict__)
        side_effect_id = "sidefx_" + _hash({
            "intent_id": intent.intent_id,
            "kind": kind,
            "target": target,
            "idempotency_key": intent.idempotency_key,
        })[:32]
        record = SideEffectRecord(
            side_effect_id=side_effect_id,
            intent_id=intent.intent_id,
            work_id=work_id,
            kind=kind,
            target=target,
            intent_hash=intent_hash,
            status="prepared",
            idempotency_key=intent.idempotency_key,
            authorization_reason=authorization.reason,
            compensation_ref=compensation_ref,
        )
        self._records[side_effect_id] = record
        self._by_idempotency[intent.idempotency_key] = side_effect_id
        return record

    def commit(self, side_effect_id: str, *, receipt_ref: str) -> SideEffectRecord:
        current = self._require(side_effect_id)
        if current.status == "committed":
            return current
        if current.status != "prepared":
            raise ValueError(f"cannot commit from {current.status}")
        if not receipt_ref.strip():
            raise ValueError("receipt_ref is required")
        updated = replace(current, status="committed", receipt_ref=receipt_ref)
        self._records[side_effect_id] = updated
        return updated

    def fail(self, side_effect_id: str, *, reason: str) -> SideEffectRecord:
        current = self._require(side_effect_id)
        if current.status != "prepared":
            raise ValueError(f"cannot fail from {current.status}")
        if not reason.strip():
            raise ValueError("failure reason is required")
        updated = replace(current, status="failed", failure_reason=reason)
        self._records[side_effect_id] = updated
        return updated

    def compensate(self, side_effect_id: str, *, receipt_ref: str) -> SideEffectRecord:
        current = self._require(side_effect_id)
        if current.status != "committed":
            raise ValueError(f"cannot compensate from {current.status}")
        if not current.compensation_ref:
            raise ValueError("no compensation plan registered")
        if not receipt_ref.strip():
            raise ValueError("compensation receipt is required")
        updated = replace(current, status="compensated", receipt_ref=receipt_ref)
        self._records[side_effect_id] = updated
        return updated

    def get(self, side_effect_id: str) -> SideEffectRecord | None:
        return self._records.get(side_effect_id)

    def _require(self, side_effect_id: str) -> SideEffectRecord:
        current = self._records.get(side_effect_id)
        if current is None:
            raise KeyError(side_effect_id)
        return current
