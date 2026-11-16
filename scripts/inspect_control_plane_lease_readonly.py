#!/usr/bin/env python3
"""Read-only, redacted SQLite lease-schema inventory for #2310 rollout planning.

This is NOT a release authorization or evidence of loaded Oracle process code.
Never instantiate ControlPlaneStore here: its constructor performs schema DDL.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from urllib.parse import quote


def inspect(db_path: Path) -> dict:
    path = Path(db_path)
    if not path.is_file():
        return {
            "schema": "agentos.lease-epoch-preflight/v1",
            "read_only": True,
            "database_exists": False,
            "schema_ready": False,
            "reason": "db_missing",
        }
    # URI open with mode=ro must never create/migrate a production database.
    uri = "file:" + quote(str(path.resolve()), safe="/") + "?mode=ro"
    with sqlite3.connect(uri, uri=True, timeout=5) as db:
        db.execute("PRAGMA query_only=ON")
        tables = {
            row[0] for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        if "tasks" not in tables:
            return {
                "schema": "agentos.lease-epoch-preflight/v1",
                "read_only": True,
                "database_exists": True,
                "schema_ready": False,
                "reason": "tasks_missing",
            }
        columns = {row[1] for row in db.execute("PRAGMA table_info(tasks)")}
        has_epoch = "lease_epoch" in columns
        now = datetime.now(timezone.utc)
        counts = Counter()
        expired = 0
        active_missing_epoch = 0
        # Aggregate only; task contents, tenant IDs, tokens, and paths never leave this tool.
        query = (
            "SELECT status, lease_until, lease_epoch FROM tasks"
            if has_epoch else "SELECT status, lease_until FROM tasks"
        )
        for row in db.execute(query):
            status = str(row[0])
            counts[status] += 1
            if status not in {"leased", "running"}:
                continue
            if has_epoch and (type(row[2]) is not int or row[2] < 1):
                active_missing_epoch += 1
            if row[1]:
                try:
                    deadline = datetime.fromisoformat(str(row[1]).replace("Z", "+00:00"))
                    if deadline.tzinfo is not None and deadline <= now:
                        expired += 1
                except ValueError:
                    # Invalid timestamp is not silently classified as healthy.
                    active_missing_epoch += 1
        return {
            "schema": "agentos.lease-epoch-preflight/v1",
            "read_only": True,
            "database_exists": True,
            "schema_ready": has_epoch,
            "migration_required": not has_epoch,
            "task_count": sum(counts.values()),
            "tasks_by_status": dict(sorted(counts.items())),
            "expired_in_flight": expired,
            "active_missing_epoch_or_invalid_deadline": active_missing_epoch,
            "rollback_fencing_proven": False,
            "old_client_compatibility_proven": False,
            "loaded_process_proven": False,
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, required=True)
    args = parser.parse_args()
    result = inspect(args.db)
    print(json.dumps(result, sort_keys=True))
    # A missing epoch or active legacy attempt must block a rollout preflight.
    return 0 if (result["schema_ready"]
                 and result["active_missing_epoch_or_invalid_deadline"] == 0) else 2


if __name__ == "__main__":
    raise SystemExit(main())
