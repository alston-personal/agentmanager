"""Governed platform execution transaction for Milkcat/AgentOS services.

A platform execution binds three concerns without merging their authorities:
- capability resolution decides whether an implementation may be reused/built;
- the credit ledger reserves and settles integer usage units;
- an append-only-ish receipt records the externally durable execution state.

Receipts are host data. The portable resolver remains persistence-free.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from runtime_core.capability_resolution import ResolutionMode

from . import config
from .capability_gate import resolve_before_build
from .credit_ledger import CreditLedger
from .governance_directory import REGISTRY_PATH


RECEIPT_SCHEMA = "milkcat.platform-execution/v0.1"
FINAL_STATES = {"succeeded", "failed"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _required(value: str, field: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{field} is required")
    return normalized


class PlatformExecutionStore:
    """Coordinates capability gating, credit settlement, and durable receipts."""

    def __init__(
        self,
        *,
        ledger: CreditLedger | None = None,
        governance_path: Path = REGISTRY_PATH,
        receipt_root: Path | str | None = None,
    ) -> None:
        self.ledger = ledger or CreditLedger()
        self.governance_path = Path(governance_path)
        self.receipt_root = Path(
            receipt_root
            or os.environ.get(
                "MILKCAT_PLATFORM_RECEIPT_ROOT",
                str(config.AGENT_DATA_ROOT / "platform" / "executions"),
            )
        )

    def _receipt_path(self, execution_id: str) -> Path:
        safe = _required(execution_id, "execution_id")
        if any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_." for ch in safe):
            raise ValueError("execution_id contains unsupported characters")
        return self.receipt_root / f"{safe}.json"

    def _save(self, receipt: dict[str, Any]) -> dict[str, Any]:
        path = self._receipt_path(str(receipt["executionId"]))
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(path)
        return receipt

    def get(self, execution_id: str) -> dict[str, Any]:
        path = self._receipt_path(execution_id)
        if not path.exists():
            raise KeyError(f"unknown platform execution: {execution_id}")
        return json.loads(path.read_text(encoding="utf-8"))

    def prepare(
        self,
        *,
        execution_id: str,
        account_id: str,
        required_capabilities: Iterable[str],
        credit_cost: int,
        allow_build_when_missing: bool = False,
        force_build: bool = False,
        override_reason: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        execution_id = _required(execution_id, "execution_id")
        account_id = _required(account_id, "account_id")

        path = self._receipt_path(execution_id)
        if path.exists():
            existing = self.get(execution_id)
            expected = {
                "accountId": account_id,
                "creditCost": credit_cost,
                "requiredCapabilities": sorted(
                    str(item) for item in required_capabilities
                ),
            }
            actual = {
                "accountId": existing.get("credits", {}).get("accountId"),
                "creditCost": existing.get("credits", {}).get("reservedAmount"),
                "requiredCapabilities": existing.get("resolution", {}).get(
                    "requiredCapabilities"
                ),
            }
            if expected != actual:
                raise ValueError("execution_id already exists with different platform parameters")
            return existing

        resolution = resolve_before_build(
            list(required_capabilities),
            path=self.governance_path,
            allow_build_when_missing=allow_build_when_missing,
            force_build=force_build,
            override_reason=override_reason,
        )
        if resolution.mode is ResolutionMode.DENY:
            raise PermissionError(resolution.reason)

        reservation = self.ledger.reserve(
            account_id,
            credit_cost,
            f"platform:{execution_id}:reserve",
            metadata={
                "execution_id": execution_id,
                "required_capabilities": list(resolution.required_capabilities),
                "resolution_mode": resolution.mode.value,
                **(metadata or {}),
            },
        )
        receipt = {
            "schema": RECEIPT_SCHEMA,
            "executionId": execution_id,
            "status": "prepared",
            "preparedAt": _now(),
            "completedAt": None,
            "resolution": {
                "mode": resolution.mode.value,
                "requiredCapabilities": list(resolution.required_capabilities),
                "selectedCandidateIds": list(resolution.selected_candidate_ids),
                "missingCapabilities": list(resolution.missing_capabilities),
                "reason": resolution.reason,
                "overrideReason": resolution.override_reason,
            },
            "credits": {
                "accountId": account_id,
                "reservedAmount": reservation["amount"],
                "reservationEntryId": reservation["entryId"],
                "committedAmount": 0,
                "releasedAmount": 0,
            },
            "metadata": dict(metadata or {}),
        }
        return self._save(receipt)

    def settle(
        self,
        execution_id: str,
        *,
        succeeded: bool,
        actual_cost: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        receipt = self.get(execution_id)
        if receipt.get("status") in FINAL_STATES:
            expected = "succeeded" if succeeded else "failed"
            if receipt["status"] != expected:
                raise ValueError(
                    f"platform execution already finalized as {receipt['status']}"
                )
            return receipt
        if receipt.get("status") != "prepared":
            raise ValueError(f"unsupported platform execution state: {receipt.get('status')}")

        reservation_id = receipt["credits"]["reservationEntryId"]
        reserved = int(receipt["credits"]["reservedAmount"])
        if succeeded:
            resolved_cost = reserved if actual_cost is None else actual_cost
            if isinstance(resolved_cost, bool) or not isinstance(resolved_cost, int):
                raise ValueError("actual_cost must be an integer")
            if resolved_cost < 0 or resolved_cost > reserved:
                raise ValueError("actual_cost must be between zero and reserved credits")

            committed = 0
            released = 0
            if resolved_cost:
                commit = self.ledger.commit(
                    reservation_id,
                    f"platform:{execution_id}:commit",
                    resolved_cost,
                    metadata={"execution_id": execution_id, **(metadata or {})},
                )
                committed = int(commit["amount"])
            if resolved_cost < reserved:
                release = self.ledger.release(
                    reservation_id,
                    f"platform:{execution_id}:release-remainder",
                    reserved - resolved_cost,
                    metadata={"execution_id": execution_id, **(metadata or {})},
                )
                released = int(release["amount"])
            status = "succeeded"
        else:
            release = self.ledger.release(
                reservation_id,
                f"platform:{execution_id}:release-failure",
                metadata={"execution_id": execution_id, **(metadata or {})},
            )
            committed = 0
            released = int(release["amount"])
            status = "failed"

        receipt["status"] = status
        receipt["completedAt"] = _now()
        receipt["credits"]["committedAmount"] = committed
        receipt["credits"]["releasedAmount"] = released
        if metadata:
            receipt.setdefault("metadata", {}).update(metadata)
        return self._save(receipt)
