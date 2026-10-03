from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agentos_node.executor_provider_registry import load_provider_profiles


SCHEMA = "agentos.executor-onboarding-plan/v0.1"
INTENT_SCHEMA = "agentos.executor-onboarding-intent/v0.1"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _state_root() -> Path:
    root = os.environ.get("AGENTOS_CLIENT_HOME")
    if root:
        return Path(root)
    return Path.home() / ".agentos"


def _fingerprint(node_id: str, provider: str, surface_id: str, kind: str) -> str:
    raw = "|".join((node_id, provider, surface_id, kind))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _profile_index(profile_root: str | Path | None = None) -> tuple[set[str], set[str]]:
    profiles = load_provider_profiles(profile_root)
    executor_ids = {str(p.get("executor_id") or "").strip() for p in profiles}
    provider_ids = {str(p.get("provider_id") or "").strip() for p in profiles}
    return executor_ids, provider_ids


def classify_surface_candidates(
    *,
    node_id: str,
    surface_inventory: dict[str, Any],
    profile_root: str | Path | None = None,
) -> list[dict[str, Any]]:
    executor_ids, provider_ids = _profile_index(profile_root)
    candidates: list[dict[str, Any]] = []

    for surface in surface_inventory.get("surfaces") or []:
        if not isinstance(surface, dict):
            continue
        provider = str(surface.get("provider") or "").strip()
        surface_id = str(surface.get("surface_id") or "").strip()
        kind = str(surface.get("kind") or "").strip()
        capabilities = {
            str(item).strip()
            for item in (surface.get("capabilities") or [])
            if str(item).strip()
        }
        if not provider or not surface_id:
            continue

        # Generic classifier: a surface must already identify itself as an
        # agent runtime or expose semantic agent capabilities. Ordinary apps,
        # shells and browser processes do not qualify merely by being present.
        looks_like_executor = (
            kind in {"agent-runtime", "ide-agent", "model-runtime"}
            or "agent.chat" in capabilities
        )
        if not looks_like_executor:
            continue

        known = provider in executor_ids or provider in provider_ids
        fingerprint = _fingerprint(node_id, provider, surface_id, kind)
        candidates.append({
            "fingerprint": fingerprint,
            "node_id": node_id,
            "provider_hint": provider,
            "surface_id": surface_id,
            "kind": kind,
            "capabilities": sorted(capabilities),
            "profile_known": known,
            "needs_profile": not known,
        })

    candidates.sort(key=lambda item: (item["provider_hint"], item["surface_id"]))
    return candidates


def _load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema": SCHEMA, "intents": {}}
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema") != SCHEMA or not isinstance(data.get("intents"), dict):
        raise ValueError("invalid executor onboarding plan")
    return data


def plan_executor_onboarding(
    *,
    node_id: str,
    surface_inventory: dict[str, Any],
    adoption: dict[str, Any],
    state_root: str | Path | None = None,
    profile_root: str | Path | None = None,
) -> dict[str, Any]:
    root = Path(state_root) if state_root is not None else _state_root()
    root.mkdir(parents=True, exist_ok=True)
    target = root / "executor-onboarding-plan.json"
    state = _load_state(target)
    intents = dict(state.get("intents") or {})

    provider_states: dict[str, str] = {}
    provider_registered: dict[str, bool] = {}
    for item in adoption.get("executors") or []:
        if not isinstance(item, dict):
            continue
        state = str(item.get("state") or "")
        registered = bool(item.get("adapter_registered"))
        for key in (str(item.get("executor_id") or "").strip(), str(item.get("provider_id") or "").strip()):
            if key:
                provider_states[key] = state
                provider_registered[key] = registered

    candidates = classify_surface_candidates(
        node_id=node_id,
        surface_inventory=surface_inventory,
        profile_root=profile_root,
    )

    queued = 0
    now = _utc_now()
    active_states = {
        "ONBOARDING_QUEUED",
        "INTEGRATION_IN_PROGRESS",
        "VALIDATING",
        "DEPLOYING",
        "SMOKE_PENDING",
        "READY",
    }

    for candidate in candidates:
        fp = candidate["fingerprint"]
        existing = intents.get(fp) or {}
        if existing.get("state") in active_states:
            continue

        provider_hint = str(candidate["provider_hint"])
        known_state = provider_states.get(provider_hint)
        if known_state == "READY":
            continue
        if candidate["profile_known"] and provider_registered.get(provider_hint) and known_state not in {None, "", "REGISTRATION_REQUIRED"}:
            # A known, registered provider that is AUTH_REQUIRED/UNHEALTHY is
            # a health/remediation problem, not an integration-code problem.
            continue

        intent = {
            "schema": INTENT_SCHEMA,
            "fingerprint": fp,
            "node_id": node_id,
            "provider_hint": provider_hint,
            "surface_id": candidate["surface_id"],
            "kind": candidate["kind"],
            "capabilities": candidate["capabilities"],
            "profile_known": bool(candidate["profile_known"]),
            "needs_profile": bool(candidate["needs_profile"]),
            "protocol": "docs/EXECUTOR_PROVIDER_ONBOARDING_PROTOCOL.md",
            "required_outputs": [
                "provider_profile",
                "provider_adapter",
                "provider_tests",
                "smoke_test",
                "receipt_contract",
            ],
            "state": "ONBOARDING_QUEUED",
            "queued_at": now,
            "attempt": int(existing.get("attempt") or 0) + 1,
        }
        intents[fp] = intent
        queued += 1

    payload = {
        "schema": SCHEMA,
        "node_id": node_id,
        "updated_at": now,
        "candidate_count": len(candidates),
        "queued_count": queued,
        "active_count": sum(
            1 for item in intents.values()
            if isinstance(item, dict) and item.get("state") in active_states
        ),
        "intents": intents,
    }
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload
