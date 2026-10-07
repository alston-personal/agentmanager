from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class WorkBindingStore:
    """Persistent scoped bindings from runtime identities to durable Work IDs."""

    SCHEMA = "agentos.work-bindings/v1"
    TERMINAL_STATES = {"completed", "failed", "cancelled", "superseded"}

    def __init__(self, path: str | Path | None = None):
        root = Path(os.environ.get("AGENT_DATA_ROOT", "/home/ubuntu/agent-data"))
        self.path = Path(path) if path is not None else root / "runtime" / "work-bindings.json"

    def _empty(self) -> dict[str, Any]:
        return {"schema": self.SCHEMA, "bindings": {}}

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return self._empty()
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if data.get("schema") != self.SCHEMA:
            raise ValueError(f"invalid Work binding store: {self.path}")
        data.setdefault("bindings", {})
        return data

    def save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(self.path)

    def list_bindings(self) -> list[dict[str, Any]]:
        data = self.load()
        return [dict(item) for item in data.get("bindings", {}).values() if isinstance(item, dict)]

    def get(self, work_id: str) -> dict[str, Any] | None:
        item = self.load().get("bindings", {}).get(str(work_id))
        return dict(item) if isinstance(item, dict) else None

    def upsert(self, binding: dict[str, Any]) -> dict[str, Any]:
        work_id = str(binding.get("work_id") or "").strip()
        if not work_id:
            raise ValueError("work_id is required")
        data = self.load()
        current = dict(data["bindings"].get(work_id) or {})
        merged = {
            **current,
            **{k: v for k, v in binding.items() if v is not None},
            "work_id": work_id,
            "updated_at": _utc_now(),
        }
        merged.setdefault("state", "active")
        data["bindings"][work_id] = merged
        self.save(data)
        return dict(merged)

    def mark_terminal(self, work_id: str, *, state: str, receipt_id: str | None = None) -> dict[str, Any] | None:
        state = str(state or "").strip()
        if state not in self.TERMINAL_STATES:
            raise ValueError(f"invalid terminal state: {state}")
        current = self.get(work_id)
        if current is None:
            return None
        update = {"work_id": work_id, "state": state}
        if receipt_id:
            update["terminal_receipt_id"] = receipt_id
        return self.upsert(update)
