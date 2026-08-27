"""Persistent store for capability-owned experience and canonical state.

This module is deliberately domain-agnostic. It persists abstract capability
experience at the capability semantic owner boundary and provides atomic state
reads/writes. Domain reducers/evaluators remain outside this store.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Iterable, Mapping

EXPERIENCE_SCHEMA = "agentos.capability-experience/v1"
STATE_SCHEMA = "agentos.capability-state/v1"


def _safe_capability_id(capability_id: str) -> str:
    value = str(capability_id or "").strip()
    if not value or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-" for c in value):
        raise ValueError("invalid capability_id")
    return value


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: Mapping[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _contains_forbidden_raw_payload(value: Any) -> bool:
    """Reject obvious raw binary/image telemetry at this shared boundary.

    Capabilities can impose stricter policies. This guard prevents the LayoutLab
    reference path from accidentally turning a capability store into an image
    archive while still allowing abstract numeric/image-dimension features.
    """
    forbidden = {"raw_image", "image_bytes", "image_base64", "pixel_data", "bitmap", "data_url"}
    if isinstance(value, Mapping):
        for key, child in value.items():
            if str(key).lower() in forbidden:
                return True
            if _contains_forbidden_raw_payload(child):
                return True
    elif isinstance(value, (list, tuple)):
        return any(_contains_forbidden_raw_payload(x) for x in value)
    return False


class CapabilityStore:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.experience_root = self.root / "experiences"
        self.state_root = self.root / "states"

    def ensure(self) -> None:
        self.experience_root.mkdir(parents=True, exist_ok=True)
        self.state_root.mkdir(parents=True, exist_ok=True)

    def _experience_dir(self, capability_id: str) -> Path:
        return self.experience_root / _safe_capability_id(capability_id)

    def _state_dir(self, capability_id: str) -> Path:
        return self.state_root / _safe_capability_id(capability_id)

    def ingest(self, experience: Mapping[str, Any]) -> dict[str, Any]:
        self.ensure()
        exp = dict(experience)
        if exp.get("schema") != EXPERIENCE_SCHEMA:
            raise ValueError("unsupported capability experience schema")
        capability_id = _safe_capability_id(str(exp.get("capability_id") or ""))
        experience_id = str(exp.get("experience_id") or "").strip()
        node_id = str(exp.get("node_id") or "").strip()
        if not experience_id or not node_id:
            raise ValueError("experience_id and node_id are required")
        if _contains_forbidden_raw_payload(exp):
            raise ValueError("raw image/binary telemetry is forbidden")

        directory = self._experience_dir(capability_id)
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / f"{experience_id}.json"
        digest = _digest(exp)
        if target.exists():
            current = json.loads(target.read_text(encoding="utf-8"))
            current_digest = _digest(current)
            if current_digest != digest:
                raise ValueError("experience_id collision with different payload")
            return {"accepted": True, "duplicate": True, "capability_id": capability_id, "experience_id": experience_id, "digest": digest}

        tmp = target.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(exp, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(tmp, target)
        return {"accepted": True, "duplicate": False, "capability_id": capability_id, "experience_id": experience_id, "digest": digest}

    def experiences(self, capability_id: str) -> list[dict[str, Any]]:
        directory = self._experience_dir(capability_id)
        if not directory.exists():
            return []
        result: list[dict[str, Any]] = []
        for path in sorted(directory.glob("*.json")):
            result.append(json.loads(path.read_text(encoding="utf-8")))
        return result

    def write_state(self, state: Mapping[str, Any], *, slot: str = "canonical") -> dict[str, Any]:
        self.ensure()
        payload = dict(state)
        if payload.get("schema") != STATE_SCHEMA:
            raise ValueError("unsupported capability state schema")
        capability_id = _safe_capability_id(str(payload.get("capability_id") or ""))
        if slot not in {"canonical", "candidate", "shadow"}:
            raise ValueError("invalid state slot")
        directory = self._state_dir(capability_id)
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / f"{slot}.json"
        tmp = target.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(tmp, target)
        return {"written": True, "slot": slot, "capability_id": capability_id, "state_id": payload.get("state_id"), "digest": _digest(payload)}

    def read_state(self, capability_id: str, *, slot: str = "canonical") -> dict[str, Any] | None:
        if slot not in {"canonical", "candidate", "shadow"}:
            raise ValueError("invalid state slot")
        target = self._state_dir(capability_id) / f"{slot}.json"
        if not target.exists():
            return None
        return json.loads(target.read_text(encoding="utf-8"))

    def ingest_many(self, experiences: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
        return [self.ingest(exp) for exp in experiences]
