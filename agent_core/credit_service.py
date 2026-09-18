"""Milkcat platform credit quoting, shadow metering, and enforce-mode settlement.

Shadow mode records intended usage without changing the immutable credit ledger.
Enforce mode uses CreditLedger reserve/commit/release so the same consumer
contract can be promoted without rewriting service integrations.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .credit_ledger import CreditLedger

MODES = {"off", "shadow", "enforce"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class CreditBilling:
    def __init__(
        self,
        *,
        ledger: CreditLedger,
        pricing_path: Path | str,
        mode: str = "shadow",
        usage_db_path: Path | str | None = None,
    ) -> None:
        if mode not in MODES:
            raise ValueError(f"unsupported billing mode: {mode}")
        self.ledger = ledger
        self.mode = mode
        self.pricing_path = Path(pricing_path)
        self.usage_db_path = Path(usage_db_path or ledger.db_path)
        self._pricing = self._load_pricing()
        self._init_usage_db()

    def _load_pricing(self) -> dict[str, int]:
        data = json.loads(self.pricing_path.read_text(encoding="utf-8"))
        if data.get("schema") != "milkcat.credit-pricing/v1":
            raise ValueError("unsupported credit pricing schema")
        actions = data.get("actions")
        if not isinstance(actions, dict):
            raise ValueError("credit pricing actions must be an object")
        normalized: dict[str, int] = {}
        for action, cost in actions.items():
            if not isinstance(action, str) or not action.strip():
                raise ValueError("credit pricing action id must be a non-empty string")
            if isinstance(cost, bool) or not isinstance(cost, int) or cost < 0:
                raise ValueError(f"credit cost must be a non-negative integer: {action}")
            normalized[action] = cost
        return normalized

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.usage_db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_usage_db(self) -> None:
        self.usage_db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS credit_usage_receipts (
                    receipt_id TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL,
                    service_id TEXT NOT NULL,
                    action_id TEXT NOT NULL,
                    operation_id TEXT NOT NULL,
                    mode TEXT NOT NULL CHECK(mode IN ('off','shadow','enforce')),
                    quoted_cost INTEGER NOT NULL CHECK(quoted_cost >= 0),
                    charged_cost INTEGER NOT NULL CHECK(charged_cost >= 0),
                    status TEXT NOT NULL,
                    reservation_id TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    UNIQUE(account_id, operation_id)
                );
                CREATE INDEX IF NOT EXISTS credit_usage_account_created
                    ON credit_usage_receipts(account_id, created_at, receipt_id);
                CREATE INDEX IF NOT EXISTS credit_usage_action_created
                    ON credit_usage_receipts(action_id, created_at, receipt_id);
                """
            )

    def quote(self, action_id: str) -> dict[str, Any]:
        action_id = str(action_id or "").strip()
        if not action_id:
            raise ValueError("action_id is required")
        if action_id not in self._pricing:
            raise KeyError(f"unknown credit action: {action_id}")
        return {
            "schema": "milkcat.credit-quote/v1",
            "actionId": action_id,
            "cost": self._pricing[action_id],
            "mode": self.mode,
        }

    @staticmethod
    def _service_from_action(action_id: str) -> str:
        return action_id.split(".", 1)[0]

    def _existing_receipt(self, account_id: str, operation_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM credit_usage_receipts WHERE account_id=? AND operation_id=?",
                (account_id, operation_id),
            ).fetchone()
        return self._receipt(row) if row else None

    @staticmethod
    def _receipt(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "schema": "milkcat.credit-usage-receipt/v1",
            "receiptId": row["receipt_id"],
            "accountId": row["account_id"],
            "serviceId": row["service_id"],
            "actionId": row["action_id"],
            "operationId": row["operation_id"],
            "mode": row["mode"],
            "quotedCost": row["quoted_cost"],
            "chargedCost": row["charged_cost"],
            "status": row["status"],
            "reservationId": row["reservation_id"],
            "metadata": json.loads(row["metadata_json"]),
            "createdAt": row["created_at"],
        }

    def _record_receipt(
        self,
        *,
        account_id: str,
        action_id: str,
        operation_id: str,
        quoted_cost: int,
        charged_cost: int,
        status: str,
        reservation_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        receipt_id = f"usage_{uuid.uuid4().hex}"
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT * FROM credit_usage_receipts WHERE account_id=? AND operation_id=?",
                (account_id, operation_id),
            ).fetchone()
            if existing:
                parsed = self._receipt(existing)
                if parsed["actionId"] != action_id:
                    raise ValueError("operation_id already used for a different credit action")
                return parsed
            connection.execute(
                """
                INSERT INTO credit_usage_receipts(
                    receipt_id, account_id, service_id, action_id, operation_id,
                    mode, quoted_cost, charged_cost, status, reservation_id,
                    metadata_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    receipt_id,
                    account_id,
                    self._service_from_action(action_id),
                    action_id,
                    operation_id,
                    self.mode,
                    quoted_cost,
                    charged_cost,
                    status,
                    reservation_id,
                    json.dumps(metadata or {}, sort_keys=True),
                    _now(),
                ),
            )
            row = connection.execute(
                "SELECT * FROM credit_usage_receipts WHERE receipt_id=?",
                (receipt_id,),
            ).fetchone()
        return self._receipt(row)

    def execute(
        self,
        *,
        account_id: str,
        action_id: str,
        operation_id: str,
        success: bool,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        account_id = str(account_id or "").strip()
        operation_id = str(operation_id or "").strip()
        if not account_id:
            raise ValueError("account_id is required")
        if not operation_id:
            raise ValueError("operation_id is required")

        existing = self._existing_receipt(account_id, operation_id)
        if existing:
            if existing["actionId"] != action_id:
                raise ValueError("operation_id already used for a different credit action")
            return existing

        quote = self.quote(action_id)
        cost = quote["cost"]

        if self.mode == "off" or cost == 0:
            return self._record_receipt(
                account_id=account_id,
                action_id=action_id,
                operation_id=operation_id,
                quoted_cost=cost,
                charged_cost=0,
                status="free" if cost == 0 else "unmetered",
                metadata=metadata,
            )

        if self.mode == "shadow":
            return self._record_receipt(
                account_id=account_id,
                action_id=action_id,
                operation_id=operation_id,
                quoted_cost=cost,
                charged_cost=0,
                status="shadow_success" if success else "shadow_failed",
                metadata=metadata,
            )

        reservation = self.ledger.reserve(
            account_id,
            cost,
            f"{operation_id}:reserve",
            metadata={"action_id": action_id, **(metadata or {})},
        )
        reservation_id = reservation["entryId"]
        if success:
            self.ledger.commit(
                reservation_id,
                f"{operation_id}:commit",
                metadata={"action_id": action_id, **(metadata or {})},
            )
            charged = cost
            status = "charged"
        else:
            self.ledger.release(
                reservation_id,
                f"{operation_id}:release",
                metadata={"action_id": action_id, **(metadata or {})},
            )
            charged = 0
            status = "released"

        return self._record_receipt(
            account_id=account_id,
            action_id=action_id,
            operation_id=operation_id,
            quoted_cost=cost,
            charged_cost=charged,
            status=status,
            reservation_id=reservation_id,
            metadata=metadata,
        )

    def usage_summary(self, account_id: str) -> dict[str, Any]:
        account_id = str(account_id or "").strip()
        if not account_id:
            raise ValueError("account_id is required")
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT action_id, COUNT(*) AS uses,
                       SUM(quoted_cost) AS quoted,
                       SUM(charged_cost) AS charged
                FROM credit_usage_receipts
                WHERE account_id=?
                GROUP BY action_id
                ORDER BY action_id
                """,
                (account_id,),
            ).fetchall()
        return {
            "accountId": account_id,
            "actions": {
                row["action_id"]: {
                    "uses": row["uses"],
                    "quotedCost": row["quoted"],
                    "chargedCost": row["charged"],
                }
                for row in rows
            },
        }
