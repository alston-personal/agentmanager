"""Off-chain integer credit ledger for AgentOS/Milkcat platform services.

The ledger is append-only. Account balance and reservation state are projections
computed from immutable entries, avoiding a second mutable source of truth.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import config


OPERATIONS = {"grant", "reserve", "commit", "release", "refund"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class CreditLedger:
    """SQLite-backed append-only credit ledger with idempotent mutations."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = Path(db_path or (config.RUNTIME_DIR / "credits.sqlite3"))
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_db(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS credit_entries (
                    entry_id TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL,
                    operation TEXT NOT NULL CHECK(operation IN ('grant','reserve','commit','release','refund')),
                    amount INTEGER NOT NULL CHECK(amount > 0),
                    reference_id TEXT,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS credit_entries_account_created
                    ON credit_entries(account_id, created_at, entry_id);
                CREATE INDEX IF NOT EXISTS credit_entries_reference
                    ON credit_entries(reference_id, operation);
                """
            )

    @staticmethod
    def _positive_amount(amount: int | None, *, field: str = "amount") -> int:
        if isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0:
            raise ValueError(f"{field} must be a positive integer")
        return amount

    @staticmethod
    def _required(value: str, field: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError(f"{field} is required")
        return normalized

    @staticmethod
    def _entry(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "entryId": row["entry_id"],
            "accountId": row["account_id"],
            "operation": row["operation"],
            "amount": row["amount"],
            "referenceId": row["reference_id"],
            "idempotencyKey": row["idempotency_key"],
            "metadata": json.loads(row["metadata_json"]),
            "createdAt": row["created_at"],
        }

    def _idempotent_existing(
        self,
        connection: sqlite3.Connection,
        *,
        idempotency_key: str,
        operation: str,
        account_id: str,
        amount: int | None,
        reference_id: str | None,
    ) -> dict[str, Any] | None:
        row = connection.execute(
            "SELECT * FROM credit_entries WHERE idempotency_key=?", (idempotency_key,)
        ).fetchone()
        if row is None:
            return None
        compatible_amount = amount is None or row["amount"] == amount
        if (
            row["operation"] != operation
            or row["account_id"] != account_id
            or row["reference_id"] != reference_id
            or not compatible_amount
        ):
            raise ValueError("idempotency key already used with different credit operation parameters")
        return self._entry(row)

    def _insert(
        self,
        connection: sqlite3.Connection,
        *,
        account_id: str,
        operation: str,
        amount: int,
        idempotency_key: str,
        reference_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        entry_id = f"credit_{uuid.uuid4().hex}"
        connection.execute(
            """
            INSERT INTO credit_entries(
                entry_id, account_id, operation, amount, reference_id,
                idempotency_key, metadata_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry_id,
                account_id,
                operation,
                amount,
                reference_id,
                idempotency_key,
                json.dumps(metadata or {}, sort_keys=True),
                _now(),
            ),
        )
        row = connection.execute(
            "SELECT * FROM credit_entries WHERE entry_id=?", (entry_id,)
        ).fetchone()
        return self._entry(row)

    def grant(
        self,
        account_id: str,
        amount: int,
        idempotency_key: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        account_id = self._required(account_id, "account_id")
        idempotency_key = self._required(idempotency_key, "idempotency_key")
        amount = self._positive_amount(amount)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = self._idempotent_existing(
                connection,
                idempotency_key=idempotency_key,
                operation="grant",
                account_id=account_id,
                amount=amount,
                reference_id=None,
            )
            if existing:
                return existing
            return self._insert(
                connection,
                account_id=account_id,
                operation="grant",
                amount=amount,
                idempotency_key=idempotency_key,
                metadata=metadata,
            )

    def reserve(
        self,
        account_id: str,
        amount: int,
        idempotency_key: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        account_id = self._required(account_id, "account_id")
        idempotency_key = self._required(idempotency_key, "idempotency_key")
        amount = self._positive_amount(amount)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = self._idempotent_existing(
                connection,
                idempotency_key=idempotency_key,
                operation="reserve",
                account_id=account_id,
                amount=amount,
                reference_id=None,
            )
            if existing:
                return existing
            if self._summary(connection, account_id)["available"] < amount:
                raise ValueError("insufficient available credits")
            return self._insert(
                connection,
                account_id=account_id,
                operation="reserve",
                amount=amount,
                idempotency_key=idempotency_key,
                metadata=metadata,
            )

    def _reservation(self, connection: sqlite3.Connection, reservation_id: str) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM credit_entries WHERE entry_id=? AND operation='reserve'", (reservation_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown reservation: {reservation_id}")
        return row

    def _reservation_totals(self, connection: sqlite3.Connection, reservation_id: str) -> dict[str, int]:
        row = connection.execute(
            """
            SELECT
              COALESCE(SUM(CASE WHEN operation='commit' THEN amount ELSE 0 END), 0) AS committed,
              COALESCE(SUM(CASE WHEN operation='release' THEN amount ELSE 0 END), 0) AS released,
              COALESCE(SUM(CASE WHEN operation='refund' THEN amount ELSE 0 END), 0) AS refunded
            FROM credit_entries WHERE reference_id=?
            """,
            (reservation_id,),
        ).fetchone()
        return {"committed": row["committed"], "released": row["released"], "refunded": row["refunded"]}

    def _reservation_mutation(
        self,
        operation: str,
        reservation_id: str,
        amount: int | None,
        idempotency_key: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if operation not in {"commit", "release", "refund"}:
            raise ValueError(f"unsupported reservation operation: {operation}")
        reservation_id = self._required(reservation_id, "reservation_id")
        idempotency_key = self._required(idempotency_key, "idempotency_key")
        if amount is not None:
            amount = self._positive_amount(amount)

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            reservation = self._reservation(connection, reservation_id)
            account_id = reservation["account_id"]
            existing = self._idempotent_existing(
                connection,
                idempotency_key=idempotency_key,
                operation=operation,
                account_id=account_id,
                amount=amount,
                reference_id=reservation_id,
            )
            if existing:
                return existing

            totals = self._reservation_totals(connection, reservation_id)
            if operation in {"commit", "release"}:
                remaining = reservation["amount"] - totals["committed"] - totals["released"]
                resolved_amount = remaining if amount is None else amount
                if resolved_amount <= 0 or resolved_amount > remaining:
                    raise ValueError(f"{operation} exceeds remaining reservation")
            else:
                refundable = totals["committed"] - totals["refunded"]
                resolved_amount = refundable if amount is None else amount
                if resolved_amount <= 0 or resolved_amount > refundable:
                    raise ValueError("refund exceeds committed credits")

            return self._insert(
                connection,
                account_id=account_id,
                operation=operation,
                amount=resolved_amount,
                idempotency_key=idempotency_key,
                reference_id=reservation_id,
                metadata=metadata,
            )

    def commit(
        self,
        reservation_id: str,
        idempotency_key: str,
        amount: int | None = None,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._reservation_mutation(
            "commit", reservation_id, amount, idempotency_key, metadata=metadata
        )

    def release(
        self,
        reservation_id: str,
        idempotency_key: str,
        amount: int | None = None,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._reservation_mutation(
            "release", reservation_id, amount, idempotency_key, metadata=metadata
        )

    def refund(
        self,
        reservation_id: str,
        idempotency_key: str,
        amount: int | None = None,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._reservation_mutation(
            "refund", reservation_id, amount, idempotency_key, metadata=metadata
        )

    def _summary(self, connection: sqlite3.Connection, account_id: str) -> dict[str, int | str]:
        balance_row = connection.execute(
            """
            SELECT COALESCE(SUM(
                CASE
                    WHEN operation IN ('grant','refund') THEN amount
                    WHEN operation='commit' THEN -amount
                    ELSE 0
                END
            ), 0) AS balance
            FROM credit_entries WHERE account_id=?
            """,
            (account_id,),
        ).fetchone()
        reserved_row = connection.execute(
            """
            SELECT COALESCE(SUM(r.amount -
                COALESCE((SELECT SUM(e.amount) FROM credit_entries e
                          WHERE e.reference_id=r.entry_id AND e.operation IN ('commit','release')), 0)
            ), 0) AS reserved
            FROM credit_entries r
            WHERE r.account_id=? AND r.operation='reserve'
            """,
            (account_id,),
        ).fetchone()
        balance = int(balance_row["balance"])
        reserved = int(reserved_row["reserved"])
        return {
            "accountId": account_id,
            "balance": balance,
            "reserved": reserved,
            "available": balance - reserved,
        }

    def summary(self, account_id: str) -> dict[str, int | str]:
        account_id = self._required(account_id, "account_id")
        with self._connect() as connection:
            return self._summary(connection, account_id)

    def entries(self, account_id: str) -> list[dict[str, Any]]:
        account_id = self._required(account_id, "account_id")
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM credit_entries WHERE account_id=? ORDER BY created_at, entry_id",
                (account_id,),
            ).fetchall()
        return [self._entry(row) for row in rows]
