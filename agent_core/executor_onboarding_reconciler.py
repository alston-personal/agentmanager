from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

from agent_core.node_registry import NodeRegistry
from agentos_node import bootstrap_control as bc


ACTION = "agentos.executor_onboarding.integrate"
STATE_SCHEMA = "agentos.executor-integrator-dispatch/v0.1"


def _safe(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._:-]+", "-", str(value or "").strip())[:120]


def _candidate_fingerprint(node_id: str, provider_hint: str, surface_id: str, kind: str) -> str:
    raw = "|".join((node_id, provider_hint, surface_id, kind))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _looks_like_executor(surface: dict[str, Any]) -> bool:
    kind = str(surface.get("kind") or "")
    caps = {str(x) for x in (surface.get("capabilities") or [])}
    return kind in {"agent-runtime", "ide-agent", "model-runtime"} or "agent.chat" in caps


def discover_core_candidates() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for node in NodeRegistry().node_map().get("nodes") or []:
        if node.get("status") != "online":
            continue
        node_id = str(node.get("node_id") or "")
        executor_inventory = node.get("executor_inventory") or {}
        known_states = {
            str(item.get("executor_id") or ""): str(item.get("state") or "")
            for item in (executor_inventory.get("executors") or [])
            if isinstance(item, dict)
        }

        for item in executor_inventory.get("executors") or []:
            if not isinstance(item, dict):
                continue
            state = str(item.get("state") or "")
            executor_id = str(item.get("executor_id") or "")
            if state != "REGISTRATION_REQUIRED" or not executor_id:
                continue
            fp = _candidate_fingerprint(node_id, executor_id, "profile:" + executor_id, "provider-profile")
            rows.append({
                "fingerprint": fp,
                "node_id": node_id,
                "provider_hint": executor_id,
                "surface_id": "profile:" + executor_id,
                "kind": "provider-profile",
                "reason": "registration_required",
            })

        for surface in (node.get("surface_inventory") or {}).get("surfaces") or []:
            if not isinstance(surface, dict) or not _looks_like_executor(surface):
                continue
            provider = str(surface.get("provider") or "").strip()
            surface_id = str(surface.get("surface_id") or "").strip()
            kind = str(surface.get("kind") or "").strip()
            if not provider or not surface_id:
                continue
            if known_states.get(provider) == "READY":
                continue
            fp = _candidate_fingerprint(node_id, provider, surface_id, kind)
            rows.append({
                "fingerprint": fp,
                "node_id": node_id,
                "provider_hint": provider,
                "surface_id": surface_id,
                "kind": kind,
                "reason": "unmanaged_surface",
            })

    dedup: dict[str, dict[str, Any]] = {}
    for row in rows:
        dedup[row["fingerprint"]] = row
    return sorted(dedup.values(), key=lambda r: (r["node_id"], r["provider_hint"], r["surface_id"]))


def _state_root() -> Path:
    root = Path(os.environ.get("AGENT_DATA_ROOT") or "/home/ubuntu/agent-data")
    path = root / "runtime" / "executor-integrator"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _load_dispatched() -> dict[str, Any]:
    path = _state_root() / "dispatch.json"
    if not path.exists():
        return {"schema": STATE_SCHEMA, "items": {}}
    doc = json.loads(path.read_text(encoding="utf-8"))
    if doc.get("schema") != STATE_SCHEMA or not isinstance(doc.get("items"), dict):
        raise ValueError("invalid executor integrator dispatch state")
    return doc


def _save_dispatched(doc: dict[str, Any]) -> None:
    path = _state_root() / "dispatch.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def enqueue_onboarding_requests() -> dict[str, Any]:
    requests, receipts, _rejected = bc._ensure(bc._root())
    state = _load_dispatched()
    items = state["items"]
    created = 0

    for candidate in discover_core_candidates():
        fp = candidate["fingerprint"]
        previous = items.get(fp) or {}
        request_id = "executor-integrate-" + fp
        receipt_path = receipts / f"{request_id}.json"

        if previous.get("state") in {"QUEUED", "DISPATCHED"}:
            continue
        if receipt_path.exists():
            previous["state"] = "DISPATCHED"
            items[fp] = previous
            continue

        target = requests / f"{request_id}.request.json"
        if target.exists():
            continue

        payload = {
            "schema": bc.SCHEMA,
            "request_id": request_id,
            "action": ACTION,
            "created_at": bc._now(),
            "params": {
                "node_id": candidate["node_id"],
                "provider_hint": candidate["provider_hint"],
                "surface_id": candidate["surface_id"],
                "fingerprint": fp,
            },
            "authority": {
                "source": "agentos-reconciler",
                "target_user": "ubuntu",
                "arbitrary_shell": False,
            },
        }
        bc._atomic_json(target, payload)
        items[fp] = {
            **candidate,
            "request_id": request_id,
            "state": "QUEUED",
            "queued_at": payload["created_at"],
        }
        created += 1

    state["items"] = items
    _save_dispatched(state)
    return {
        "schema": STATE_SCHEMA,
        "candidate_count": len(discover_core_candidates()),
        "created_count": created,
        "active_count": sum(1 for x in items.values() if x.get("state") in {"QUEUED", "DISPATCHED"}),
    }
