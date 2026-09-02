from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from agent_core.employee_lifecycle import EmployeeLifecycle


MESSAGE_SCHEMA = "agentos.employee-realm-message/v1"
CLAIM_SCHEMA = "agentos.employee-realm-message-claim/v1"
RECEIPT_SCHEMA = "agentos.employee-realm-message-receipt/v1"
MESSAGE_KINDS = {"handoff", "finding", "question", "answer", "notification"}
RECEIPT_DISPOSITIONS = {"processed", "deferred", "rejected"}
MAX_SUBJECT_CHARS = 160
MAX_SUMMARY_CHARS = 4000
MAX_REFS = 32
MAX_REF_CHARS = 256
MAX_CLAIM_SECONDS = 600
SECRET_MARKERS = (
    "bearer ",
    "github_pat_",
    "ghp_",
    "token=",
    "secret=",
    "authorization:",
)
FORBIDDEN_REF_MARKERS = ("://", "\\", "../", "..\\")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None = None) -> str:
    return (value or _now()).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)


def _safe_id(value: str) -> str:
    value = str(value or "").strip()
    if not value or any(ch in value for ch in "/\\\0") or value in {".", ".."}:
        raise ValueError("unsafe_employee_message_id")
    return value


def _safe_text(value: str, *, limit: int, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field}_required")
    if len(text) > limit:
        raise ValueError(f"{field}_too_long")
    lowered = text.casefold()
    if any(marker in lowered for marker in SECRET_MARKERS):
        raise ValueError(f"{field}_contains_secret_like_value")
    return text


def _safe_ref(value: str) -> str:
    ref = str(value or "").strip()
    if not ref or len(ref) > MAX_REF_CHARS:
        raise ValueError("invalid_employee_message_ref")
    lowered = ref.casefold()
    if any(marker in lowered for marker in SECRET_MARKERS):
        raise ValueError("employee_message_ref_contains_secret_like_value")
    if ref.startswith(("/", "~")) or any(marker in ref for marker in FORBIDDEN_REF_MARKERS):
        raise ValueError("employee_message_ref_must_be_logical")
    if ":" not in ref:
        raise ValueError("employee_message_ref_must_be_typed")
    return ref


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
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
        raise ValueError("employee_message_state_invalid")
    return payload


def _message_digest(payload: dict[str, Any]) -> str:
    canonical = {
        key: payload.get(key)
        for key in (
            "sender_employee_id",
            "recipient_employee_id",
            "kind",
            "subject",
            "summary",
            "assignment_ref",
            "thread_ref",
            "artifact_refs",
        )
    }
    raw = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass(slots=True)
class RealmEmployeeMessage:
    schema: str
    message_id: str
    digest: str
    sender_employee_id: str
    recipient_employee_id: str
    kind: str
    subject: str
    summary: str
    assignment_ref: str | None
    thread_ref: str | None
    artifact_refs: list[str]
    created_at: str
    state: str = "queued"
    delivery_generation: int = 0
    active_claim_id: str | None = None
    active_claim_expires_at: str | None = None
    acknowledged_at: str | None = None
    receipt_id: str | None = None


@dataclass(frozen=True, slots=True)
class RealmEmployeeMessageClaim:
    schema: str
    message_id: str
    claim_id: str
    recipient_employee_id: str
    recipient_assignment_id: str
    delivery_generation: int
    claimed_at: str
    expires_at: str
    redelivery_required: bool
    prior_delivery_state: str
    transport: str = "one_resident_mailbox"
    node_selection: str = "unbound"
    executor_selection: str = "unbound"
    credential_exposed: bool = False


@dataclass(frozen=True, slots=True)
class RealmEmployeeMessageReceipt:
    schema: str
    receipt_id: str
    message_id: str
    claim_id: str
    recipient_employee_id: str
    recipient_assignment_id: str
    delivery_generation: int
    disposition: str
    acknowledged_at: str
    transport: str = "one_resident_mailbox"
    credential_exposed: bool = False


class EmployeeRealmMailbox:
    """ONE/Core-resident durable mailbox addressed by Employee identity.

    The mailbox is deliberately independent of Node/model/session location.  A
    message remains in ONE until a worker that currently owns an assignment for
    the recipient Employee claims and acknowledges it.  This module chooses no
    Node, executor, external transport or capability carrier.
    """

    def __init__(self, lifecycle: EmployeeLifecycle) -> None:
        self.lifecycle = lifecycle
        self.root = lifecycle.root / "realm" / "employee-mailbox"
        self.messages_dir = self.root / "messages"
        self.receipts_dir = self.root / "receipts"

    def _message_path(self, recipient_employee_id: str, message_id: str) -> Path:
        return self.messages_dir / _safe_id(recipient_employee_id) / f"{_safe_id(message_id)}.json"

    def _receipt_path(self, message_id: str, generation: int) -> Path:
        return self.receipts_dir / _safe_id(message_id) / f"{int(generation)}.json"

    def _find_message_path(self, message_id: str) -> Path:
        message_id = _safe_id(message_id)
        matches = list(self.messages_dir.glob(f"*/{message_id}.json"))
        if not matches:
            raise FileNotFoundError(message_id)
        if len(matches) > 1:
            raise RuntimeError("duplicate_employee_message_id")
        return matches[0]

    def get(self, message_id: str) -> RealmEmployeeMessage:
        payload = _read(self._find_message_path(message_id))
        if payload is None:
            raise FileNotFoundError(message_id)
        if payload.get("schema") != MESSAGE_SCHEMA:
            raise ValueError("employee_message_schema_invalid")
        return RealmEmployeeMessage(**payload)

    def send(
        self,
        sender_employee_id: str,
        sender_assignment_id: str,
        sender_lease_id: str,
        recipient_employee_id: str,
        message_id: str,
        *,
        kind: str,
        subject: str,
        summary: str,
        assignment_ref: str | None = None,
        thread_ref: str | None = None,
        artifact_refs: list[str] | None = None,
        now: datetime | None = None,
    ) -> RealmEmployeeMessage:
        sender_employee_id = _safe_id(sender_employee_id)
        recipient_employee_id = _safe_id(recipient_employee_id)
        message_id = _safe_id(message_id)
        kind = str(kind or "").strip()
        if kind not in MESSAGE_KINDS:
            raise ValueError("employee_message_kind_not_allowed")

        self.lifecycle.runtime.get_employee(sender_employee_id)
        self.lifecycle.runtime.get_employee(recipient_employee_id)
        self.lifecycle._require_current_active(  # noqa: SLF001
            sender_assignment_id,
            sender_lease_id,
            now=now,
        )
        sender_assignment = self.lifecycle.runtime.get_assignment(sender_assignment_id)
        if sender_assignment.employee_id != sender_employee_id:
            raise PermissionError("sender_assignment_employee_mismatch")

        refs = list(artifact_refs or [])
        if len(refs) > MAX_REFS:
            raise ValueError("employee_message_too_many_refs")
        normalized_refs = [_safe_ref(value) for value in refs]
        normalized_assignment_ref = _safe_ref(assignment_ref) if assignment_ref else None
        normalized_thread_ref = _safe_ref(thread_ref) if thread_ref else None

        candidate = RealmEmployeeMessage(
            schema=MESSAGE_SCHEMA,
            message_id=message_id,
            digest="",
            sender_employee_id=sender_employee_id,
            recipient_employee_id=recipient_employee_id,
            kind=kind,
            subject=_safe_text(subject, limit=MAX_SUBJECT_CHARS, field="subject"),
            summary=_safe_text(summary, limit=MAX_SUMMARY_CHARS, field="summary"),
            assignment_ref=normalized_assignment_ref,
            thread_ref=normalized_thread_ref,
            artifact_refs=normalized_refs,
            created_at=_iso(now),
        )
        raw = asdict(candidate)
        raw["digest"] = _message_digest(raw)
        candidate.digest = raw["digest"]
        path = self._message_path(recipient_employee_id, message_id)
        existing = _read(path)
        if existing is not None:
            if existing.get("digest") != candidate.digest:
                raise RuntimeError("employee_message_idempotency_conflict")
            return RealmEmployeeMessage(**existing)
        _atomic_write(path, raw)
        return candidate

    def pending(self, recipient_employee_id: str, *, now: datetime | None = None) -> list[RealmEmployeeMessage]:
        recipient_employee_id = _safe_id(recipient_employee_id)
        self.lifecycle.runtime.get_employee(recipient_employee_id)
        current = now or _now()
        inbox = self.messages_dir / recipient_employee_id
        if not inbox.exists():
            return []
        result: list[RealmEmployeeMessage] = []
        for path in sorted(inbox.glob("*.json")):
            payload = _read(path)
            if not payload or payload.get("schema") != MESSAGE_SCHEMA:
                continue
            message = RealmEmployeeMessage(**payload)
            if message.state == "acknowledged":
                continue
            if message.state == "claimed" and message.active_claim_expires_at:
                if _parse(message.active_claim_expires_at) > current:
                    continue
            result.append(message)
        return result

    def claim(
        self,
        message_id: str,
        recipient_employee_id: str,
        recipient_assignment_id: str,
        recipient_lease_id: str,
        claim_id: str,
        *,
        claim_seconds: int = 120,
        now: datetime | None = None,
    ) -> RealmEmployeeMessageClaim:
        message_id = _safe_id(message_id)
        recipient_employee_id = _safe_id(recipient_employee_id)
        claim_id = _safe_id(claim_id)
        current = now or _now()
        claim_seconds = max(15, min(int(claim_seconds), MAX_CLAIM_SECONDS))

        self.lifecycle._require_current_active(  # noqa: SLF001
            recipient_assignment_id,
            recipient_lease_id,
            now=current,
        )
        assignment = self.lifecycle.runtime.get_assignment(recipient_assignment_id)
        if assignment.employee_id != recipient_employee_id:
            raise PermissionError("recipient_assignment_employee_mismatch")

        path = self._find_message_path(message_id)
        payload = _read(path)
        if payload is None:
            raise FileNotFoundError(message_id)
        message = RealmEmployeeMessage(**payload)
        if message.recipient_employee_id != recipient_employee_id:
            raise PermissionError("employee_message_recipient_mismatch")
        if message.state == "acknowledged":
            raise RuntimeError("employee_message_already_acknowledged")

        prior_unknown = False
        if message.state == "claimed" and message.active_claim_id:
            expires = _parse(message.active_claim_expires_at or "1970-01-01T00:00:00Z")
            if expires > current:
                if message.active_claim_id == claim_id:
                    return RealmEmployeeMessageClaim(
                        schema=CLAIM_SCHEMA,
                        message_id=message_id,
                        claim_id=claim_id,
                        recipient_employee_id=recipient_employee_id,
                        recipient_assignment_id=recipient_assignment_id,
                        delivery_generation=message.delivery_generation,
                        claimed_at=payload.get("active_claimed_at") or _iso(current),
                        expires_at=message.active_claim_expires_at or _iso(current),
                        redelivery_required=message.delivery_generation > 1,
                        prior_delivery_state="unknown" if message.delivery_generation > 1 else "known",
                    )
                raise RuntimeError("employee_message_already_claimed")
            prior_unknown = True

        generation = message.delivery_generation + 1
        claimed_at = _iso(current)
        expires_at = _iso(current + timedelta(seconds=claim_seconds))
        payload.update(
            {
                "state": "claimed",
                "delivery_generation": generation,
                "active_claim_id": claim_id,
                "active_claimed_at": claimed_at,
                "active_claim_expires_at": expires_at,
            }
        )
        _atomic_write(path, payload)
        return RealmEmployeeMessageClaim(
            schema=CLAIM_SCHEMA,
            message_id=message_id,
            claim_id=claim_id,
            recipient_employee_id=recipient_employee_id,
            recipient_assignment_id=recipient_assignment_id,
            delivery_generation=generation,
            claimed_at=claimed_at,
            expires_at=expires_at,
            redelivery_required=prior_unknown,
            prior_delivery_state="unknown" if prior_unknown else "known",
        )

    def acknowledge(
        self,
        message_id: str,
        recipient_employee_id: str,
        recipient_assignment_id: str,
        recipient_lease_id: str,
        claim_id: str,
        *,
        disposition: str = "processed",
        now: datetime | None = None,
    ) -> RealmEmployeeMessageReceipt:
        message_id = _safe_id(message_id)
        recipient_employee_id = _safe_id(recipient_employee_id)
        claim_id = _safe_id(claim_id)
        disposition = str(disposition or "").strip()
        if disposition not in RECEIPT_DISPOSITIONS:
            raise ValueError("employee_message_disposition_not_allowed")
        current = now or _now()

        self.lifecycle._require_current_active(  # noqa: SLF001
            recipient_assignment_id,
            recipient_lease_id,
            now=current,
        )
        assignment = self.lifecycle.runtime.get_assignment(recipient_assignment_id)
        if assignment.employee_id != recipient_employee_id:
            raise PermissionError("recipient_assignment_employee_mismatch")

        path = self._find_message_path(message_id)
        payload = _read(path)
        if payload is None:
            raise FileNotFoundError(message_id)
        message = RealmEmployeeMessage(**{
            key: value
            for key, value in payload.items()
            if key in RealmEmployeeMessage.__dataclass_fields__
        })
        if message.recipient_employee_id != recipient_employee_id:
            raise PermissionError("employee_message_recipient_mismatch")
        if message.state == "acknowledged":
            receipt_payload = _read(self._receipt_path(message_id, message.delivery_generation))
            if receipt_payload is None:
                raise RuntimeError("employee_message_receipt_missing")
            return RealmEmployeeMessageReceipt(**receipt_payload)
        if message.state != "claimed" or message.active_claim_id != claim_id:
            raise PermissionError("employee_message_claim_not_owned")
        if not message.active_claim_expires_at or _parse(message.active_claim_expires_at) <= current:
            raise RuntimeError("employee_message_claim_expired")

        receipt_id = "msgreceipt_" + hashlib.sha256(
            f"{message_id}\0{message.delivery_generation}\0{claim_id}\0{disposition}".encode("utf-8")
        ).hexdigest()[:24]
        receipt = RealmEmployeeMessageReceipt(
            schema=RECEIPT_SCHEMA,
            receipt_id=receipt_id,
            message_id=message_id,
            claim_id=claim_id,
            recipient_employee_id=recipient_employee_id,
            recipient_assignment_id=recipient_assignment_id,
            delivery_generation=message.delivery_generation,
            disposition=disposition,
            acknowledged_at=_iso(current),
        )
        # Receipt is persisted before message terminal state so an interrupted
        # acknowledgement can be recovered without inventing a successful ack.
        _atomic_write(self._receipt_path(message_id, message.delivery_generation), asdict(receipt))
        payload.update(
            {
                "state": "acknowledged",
                "acknowledged_at": receipt.acknowledged_at,
                "receipt_id": receipt.receipt_id,
            }
        )
        _atomic_write(path, payload)
        return receipt
