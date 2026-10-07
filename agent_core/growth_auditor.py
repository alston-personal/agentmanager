from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

LEDGER_SCHEMA = "agentos.growth-proof-ledger/v1"
EVIDENCE_SCHEMA = "agentos.growth-evidence/v1"
VALID_LEVELS = {"G0", "G1", "G2", "G3", "G4", "G5"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _stable(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def evidence_id(payload: dict[str, Any]) -> str:
    raw = {
        "source_experience": payload.get("source_experience"),
        "new_task": payload.get("new_task"),
        "candidate_id": payload.get("candidate_id"),
        "reuse_boundary": payload.get("reuse_boundary"),
        "metrics_before": payload.get("metrics_before"),
        "metrics_after": payload.get("metrics_after"),
        "verdict": payload.get("verdict"),
    }
    return "gp-" + hashlib.sha256(_stable(raw).encode("utf-8")).hexdigest()[:20]


@dataclass
class GrowthAuditor:
    data_root: Path

    def __post_init__(self) -> None:
        self.data_root = Path(self.data_root)
        self.path = self.data_root / "growth-proof" / "ledger.json"

    def _empty(self) -> dict[str, Any]:
        return {
            "schema": LEDGER_SCHEMA,
            "revision": 0,
            "updated_at": None,
            "evidence": {},
            "metrics": {
                "observations_total": 0,
                "qualified_total": 0,
                "g3_or_above_total": 0,
                "cross_boundary_total": 0,
            },
        }

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return self._empty()
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if data.get("schema") != LEDGER_SCHEMA:
            raise ValueError(f"invalid growth ledger schema: {data.get('schema')}")
        data.setdefault("evidence", {})
        data.setdefault("metrics", self._empty()["metrics"])
        return data

    def save(self, ledger: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        ledger["revision"] = int(ledger.get("revision") or 0) + 1
        ledger["updated_at"] = _utc_now()
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(ledger, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(self.path)

    @staticmethod
    def classify(observation: dict[str, Any]) -> str | None:
        explicit = str(observation.get("verdict") or "").upper()
        if explicit in VALID_LEVELS:
            return explicit

        has_source = bool(observation.get("source_experience"))
        has_candidate = bool(observation.get("candidate_id") or observation.get("transferred_pattern"))
        reused = bool(observation.get("independent_reuse"))
        before = observation.get("metrics_before") or {}
        after = observation.get("metrics_after") or {}
        measured = bool(before and after)
        boundary = str(observation.get("reuse_boundary") or "same-session")

        if not has_source:
            return None
        if not has_candidate:
            return "G0"
        if not reused:
            return "G1"
        if not measured:
            return "G2"
        if boundary not in {"same-session", "same-executor", "same-node", ""}:
            return "G4"
        return "G3"

    @staticmethod
    def _uplift(before: dict[str, Any], after: dict[str, Any]) -> dict[str, float]:
        result: dict[str, float] = {}
        for key, old in before.items():
            new = after.get(key)
            if isinstance(old, (int, float)) and isinstance(new, (int, float)):
                result[key] = float(new) - float(old)
        return result

    def observe(self, observation: dict[str, Any]) -> dict[str, Any]:
        ledger = self.load()
        level = self.classify(observation)
        ledger["metrics"]["observations_total"] = int(ledger["metrics"].get("observations_total") or 0) + 1

        if level is None:
            self.save(ledger)
            return {"qualified": False, "reason": "no_source_experience"}

        payload = {
            "schema": EVIDENCE_SCHEMA,
            "captured_at": _utc_now(),
            "source_experience": observation.get("source_experience"),
            "new_task": observation.get("new_task"),
            "candidate_id": observation.get("candidate_id"),
            "transferred_pattern": observation.get("transferred_pattern"),
            "independent_reuse": bool(observation.get("independent_reuse")),
            "reuse_boundary": observation.get("reuse_boundary") or "same-session",
            "controlled_variables": dict(observation.get("controlled_variables") or {}),
            "changed_variable": observation.get("changed_variable") or "validated accumulated experience",
            "metrics_before": dict(observation.get("metrics_before") or {}),
            "metrics_after": dict(observation.get("metrics_after") or {}),
            "regressions": list(observation.get("regressions") or []),
            "evidence": list(observation.get("evidence") or []),
            "verdict": level,
        }
        payload["uplift"] = self._uplift(payload["metrics_before"], payload["metrics_after"])
        payload["proof_id"] = evidence_id(payload)

        previous = ledger["evidence"].get(payload["proof_id"])
        ledger["evidence"][payload["proof_id"]] = payload

        if previous is None:
            ledger["metrics"]["qualified_total"] = int(ledger["metrics"].get("qualified_total") or 0) + 1
            if level in {"G3", "G4", "G5"}:
                ledger["metrics"]["g3_or_above_total"] = int(ledger["metrics"].get("g3_or_above_total") or 0) + 1
            if level in {"G4", "G5"}:
                ledger["metrics"]["cross_boundary_total"] = int(ledger["metrics"].get("cross_boundary_total") or 0) + 1

        self.save(ledger)
        return {"qualified": True, "proof": payload, "deduplicated": previous is not None}

    def observe_many(self, observations: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
        return [self.observe(item) for item in observations]
