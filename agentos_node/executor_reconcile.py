from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from agentos_node.executor_provider_registry import (
    load_provider,
    load_provider_profiles,
)


SCHEMA = "agentos.executor-inventory/v0.2"
ADOPTION_SCHEMA = "agentos.executor-adoption/v0.2"


def _state_root() -> Path:
    root = os.environ.get("AGENTOS_CLIENT_HOME")
    if root:
        return Path(root)
    return Path.home() / ".agentos"


def _bounded_error(exc: Exception) -> str:
    return type(exc).__name__


def _state_from_provider(
    profile: dict[str, Any],
    provider: Any | None,
) -> dict[str, Any]:
    executor_id = str(profile["executor_id"])
    base: dict[str, Any] = {
        "executor_id": executor_id,
        "provider_id": str(profile["provider_id"]),
        "executor_class": str(profile["executor_class"]),
        "modes": list(profile.get("modes") or []),
        "capabilities": sorted({
            str(item).strip()
            for item in (profile.get("capabilities") or [])
            if str(item).strip()
        }),
        "profile_valid": True,
        "adapter_registered": provider is not None,
        "adoptable": provider is not None,
        "routable": False,
    }

    if provider is None:
        base.update({
            "state": "REGISTRATION_REQUIRED",
            "discovered": False,
            "authorized": False,
            "healthy": False,
        })
        return base

    try:
        discovered = provider.discover()
        if not isinstance(discovered, dict):
            raise ValueError("discover() must return object")
    except Exception as exc:
        base.update({
            "state": "UNHEALTHY",
            "discovered": False,
            "authorized": False,
            "healthy": False,
            "provider_error": _bounded_error(exc),
        })
        return base

    try:
        health = provider.health()
        if not isinstance(health, dict):
            raise ValueError("health() must return object")
    except Exception as exc:
        base.update({
            "state": "UNHEALTHY",
            "discovered": bool(discovered.get("installed") or discovered.get("detected")),
            "authorized": False,
            "healthy": False,
            "provider_error": _bounded_error(exc),
        })
        return base

    installed = bool(discovered.get("installed") or discovered.get("detected"))
    reachable = bool(health.get("reachable", installed))
    authorized = bool(health.get("authorized"))
    routable = bool(health.get("routable"))
    healthy = bool(health.get("healthy"))

    base.update({
        "discovered": installed,
        "reachable": reachable,
        "authorized": authorized,
        "healthy": healthy,
        "provider_health": {
            key: health.get(key)
            for key in (
                "classification",
                "reachable",
                "authorized",
                "routable",
                "healthy",
                "busy",
                "rate_limited",
            )
            if key in health
        },
    })

    if not installed:
        state = str(health.get("state") or "INSTALL_REQUIRED")
    elif not reachable:
        state = str(health.get("state") or "UNHEALTHY")
    elif not authorized:
        state = str(health.get("state") or "AUTH_REQUIRED")
    elif not healthy:
        state = str(health.get("state") or "UNHEALTHY")
    elif not routable:
        state = str(health.get("state") or "DISCOVERED")
    else:
        state = "READY"

    base["state"] = state
    base["routable"] = state == "READY"
    return base


def discover_executor_inventory(
    *,
    profile_root: str | Path | None = None,
) -> dict[str, Any]:
    executors: list[dict[str, Any]] = []
    for profile in load_provider_profiles(profile_root):
        try:
            provider = load_provider(profile)
            executors.append(_state_from_provider(profile, provider))
        except Exception as exc:
            executors.append({
                "executor_id": str(profile.get("executor_id") or "unknown"),
                "provider_id": str(profile.get("provider_id") or "unknown"),
                "executor_class": str(profile.get("executor_class") or "unknown"),
                "profile_valid": True,
                "adapter_registered": False,
                "adoptable": False,
                "routable": False,
                "state": "REGISTRATION_REQUIRED",
                "provider_error": _bounded_error(exc),
            })

    return {
        "schema": SCHEMA,
        "provider_profile_schema": "agentos.executor-provider-profile/v0.1",
        "executors": executors,
    }


def reconcile_executor_adoption(
    *,
    state_root: str | Path | None = None,
    profile_root: str | Path | None = None,
) -> dict[str, Any]:
    root = Path(state_root) if state_root is not None else _state_root()
    root.mkdir(parents=True, exist_ok=True)

    inventory = discover_executor_inventory(profile_root=profile_root)
    adopted = [
        {
            "executor_id": item["executor_id"],
            "provider_id": item.get("provider_id"),
            "executor_class": item.get("executor_class"),
            "state": item["state"],
            "adopted": bool(item.get("adoptable")),
            "routable": bool(item.get("routable")),
            "capabilities": list(item.get("capabilities") or []),
            "profile_valid": bool(item.get("profile_valid")),
            "adapter_registered": bool(item.get("adapter_registered")),
            "discovered": bool(item.get("discovered")),
            "authorized": bool(item.get("authorized")),
            "healthy": bool(item.get("healthy")),
        }
        for item in inventory["executors"]
    ]

    counts: dict[str, int] = {}
    for item in adopted:
        state = str(item["state"])
        counts[state] = counts.get(state, 0) + 1

    payload = {
        "schema": ADOPTION_SCHEMA,
        "inventory_schema": inventory["schema"],
        "provider_profile_schema": inventory["provider_profile_schema"],
        "executors": adopted,
        "summary": {
            "total": len(adopted),
            "ready": counts.get("READY", 0),
            "by_state": dict(sorted(counts.items())),
        },
    }

    target = root / "executor-adoption.json"
    fd, temp_name = tempfile.mkstemp(
        prefix=".executor-adoption-",
        suffix=".json",
        dir=str(root),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temp_name, target)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)

    return {
        "executor_adoption": payload,
        "state_path": str(target),
        "ok": True,
    }
