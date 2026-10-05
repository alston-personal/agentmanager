from __future__ import annotations

import json
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agentos_node.executor_provider_registry import (
    load_provider,
    load_provider_profiles,
)


SCHEMA = "agentos.executor-inventory/v0.2"
ADOPTION_SCHEMA = "agentos.executor-adoption/v0.2"
CLAUDE_TIMEOUT_COOLDOWN_SECONDS = 300.0


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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
    *,
    probe_health: bool = True,
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
        error_type = _bounded_error(exc)
        base.update({
            "state": "UNHEALTHY",
            "discovered": False,
            "authorized": False,
            "healthy": False,
            "provider_error": error_type,
            "provider_health": {"classification": "PROVIDER_EXCEPTION_" + error_type.upper()},
        })
        return base

    if not probe_health:
        installed = bool(discovered.get("installed") or discovered.get("detected"))
        base.update({
            "state": "DISCOVERED" if installed else "INSTALL_REQUIRED",
            "discovered": installed,
            "reachable": False,
            "authorized": False,
            "healthy": False,
            "routable": False,
            "health_deferred": True,
        })
        return base

    try:
        health = provider.health()
        if not isinstance(health, dict):
            raise ValueError("health() must return object")
    except Exception as exc:
        error_type = _bounded_error(exc)
        base.update({
            "state": "UNHEALTHY",
            "discovered": bool(discovered.get("installed") or discovered.get("detected")),
            "authorized": False,
            "healthy": False,
            "provider_error": error_type,
            "provider_health": {"classification": "PROVIDER_EXCEPTION_" + error_type.upper()},
        })
        return base

    installed = bool(discovered.get("installed") or discovered.get("detected"))
    reachable = bool(health.get("reachable", installed))
    authorized = bool(health.get("authorized"))
    routable = bool(health.get("routable"))
    healthy = bool(health.get("healthy"))

    provider_health = {
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
    }
    if not str(provider_health.get("classification") or "").strip():
        health_state = str(health.get("state") or "").strip()
        if health_state == "AUTH_REQUIRED":
            provider_health["classification"] = "AUTH_REQUIRED"
        elif not installed:
            provider_health["classification"] = "INSTALL_REQUIRED"
        elif not reachable:
            provider_health["classification"] = "UNREACHABLE"
        elif not healthy or not routable or not authorized:
            provider_health["classification"] = "UNCLASSIFIED_UNHEALTHY"

    base.update({
        "discovered": installed,
        "reachable": reachable,
        "authorized": authorized,
        "healthy": healthy,
        "provider_health": provider_health,
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
    probe_health: bool = True,
    deferred_health: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    profiles = load_provider_profiles(profile_root)

    deferred_health = deferred_health or {}

    def inspect_profile(profile: dict[str, Any]) -> dict[str, Any]:
        try:
            provider = load_provider(profile)
            executor_id = str(profile.get("executor_id") or "")
            prior = deferred_health.get(executor_id)
            if probe_health and isinstance(prior, dict):
                current = _state_from_provider(profile, provider, probe_health=False)
                if current.get("discovered") is True:
                    current.update({
                        "state": str(prior.get("state") or "UNHEALTHY"),
                        "reachable": bool(prior.get("reachable")),
                        "authorized": bool(prior.get("authorized")),
                        "healthy": bool(prior.get("healthy")),
                        "routable": False,
                        "provider_health": dict(prior.get("provider_health") or {}),
                        "provider_error": str(prior.get("provider_error") or ""),
                        "health_deferred": True,
                    })
                return current
            return _state_from_provider(profile, provider, probe_health=probe_health)
        except Exception as exc:
            return {
                "executor_id": str(profile.get("executor_id") or "unknown"),
                "provider_id": str(profile.get("provider_id") or "unknown"),
                "executor_class": str(profile.get("executor_class") or "unknown"),
                "profile_valid": True,
                "adapter_registered": False,
                "adoptable": False,
                "routable": False,
                "state": "REGISTRATION_REQUIRED",
                "provider_error": _bounded_error(exc),
            }

    # Provider health probes are independent bounded operations. Run them
    # concurrently so one slow provider (for example, a 60s timeout) does not
    # serialize every other provider probe. executor order remains canonical
    # because executor.map preserves input ordering.
    if probe_health and len(profiles) > 1:
        workers = min(4, len(profiles))
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="executor-health") as pool:
            executors = list(pool.map(inspect_profile, profiles))
    else:
        executors = [inspect_profile(profile) for profile in profiles]

    return {
        "schema": SCHEMA,
        "provider_profile_schema": "agentos.executor-provider-profile/v0.1",
        "executors": executors,
    }


def reconcile_executor_adoption(
    *,
    node_id: str = "local-node",
    state_root: str | Path | None = None,
    profile_root: str | Path | None = None,
) -> dict[str, Any]:
    root = Path(state_root) if state_root is not None else _state_root()
    root.mkdir(parents=True, exist_ok=True)

    previous_by_executor: dict[str, dict[str, Any]] = {}
    previous_path = root / "executor-adoption.json"
    if previous_path.exists():
        try:
            previous = json.loads(previous_path.read_text(encoding="utf-8"))
            if previous.get("schema") == ADOPTION_SCHEMA:
                previous_by_executor = {
                    str(item.get("executor_id") or ""): item
                    for item in previous.get("executors") or []
                    if isinstance(item, dict) and item.get("executor_id")
                }
        except Exception:
            previous_by_executor = {}

    now_text = _utc_now()
    now = datetime.fromisoformat(now_text.replace("Z", "+00:00"))
    deferred_health: dict[str, dict[str, Any]] = {}
    prior_claude = previous_by_executor.get("claude-code") or {}
    prior_classification = str((prior_claude.get("provider_health") or {}).get("classification") or "")
    last_probed_text = str(prior_claude.get("last_probed_at") or "")
    if prior_classification == "TIMEOUT" and last_probed_text:
        try:
            last_probed = datetime.fromisoformat(last_probed_text.replace("Z", "+00:00"))
            age = (now - last_probed.astimezone(timezone.utc)).total_seconds()
        except Exception:
            age = CLAUDE_TIMEOUT_COOLDOWN_SECONDS
        if 0 <= age < CLAUDE_TIMEOUT_COOLDOWN_SECONDS:
            deferred_health["claude-code"] = prior_claude

    inventory = discover_executor_inventory(
        profile_root=profile_root,
        deferred_health=deferred_health,
    )

    adopted = []
    for item in inventory["executors"]:
        executor_id = str(item["executor_id"])
        prior = previous_by_executor.get(executor_id) or {}
        ready_streak = int(prior.get("ready_streak") or 0) + 1 if item["state"] == "READY" else 0
        adopted.append({
            "executor_id": executor_id,
            "provider_id": item.get("provider_id"),
            "executor_class": item.get("executor_class"),
            "state": item["state"],
            "adopted": bool(item.get("adoptable")),
            "routable": bool(item.get("routable")),
            "stable_routable": bool(item.get("routable")) and ready_streak >= 2,
            "ready_streak": ready_streak,
            "capabilities": list(item.get("capabilities") or []),
            "profile_valid": bool(item.get("profile_valid")),
            "adapter_registered": bool(item.get("adapter_registered")),
            "discovered": bool(item.get("discovered")),
            "reachable": bool(item.get("reachable")),
            "authorized": bool(item.get("authorized")),
            "healthy": bool(item.get("healthy")),
            "provider_health": dict(item.get("provider_health") or {}),
            "provider_error": str(item.get("provider_error") or ""),
            "health_deferred": item.get("health_deferred") is True,
            "last_probed_at": (
                str(prior.get("last_probed_at") or "")
                if item.get("health_deferred") is True
                else now_text
            ),
        })

    counts: dict[str, int] = {}
    for item in adopted:
        state = str(item["state"])
        counts[state] = counts.get(state, 0) + 1

    payload = {
        "schema": ADOPTION_SCHEMA,
        "observed_at": now_text,
        "inventory_schema": inventory["schema"],
        "provider_profile_schema": inventory["provider_profile_schema"],
        "executors": adopted,
        "summary": {
            "total": len(adopted),
            "ready": counts.get("READY", 0),
            "by_state": dict(sorted(counts.items())),
        },
    }

    try:
        from agentos_node.agent_surfaces import discover_surfaces
        from agentos_node.executor_onboarding import plan_executor_onboarding
        onboarding = plan_executor_onboarding(
            node_id=node_id,
            surface_inventory=discover_surfaces(),
            adoption=payload,
            state_root=root,
            profile_root=profile_root,
        )
    except Exception as exc:
        onboarding = {
            "schema": "agentos.executor-onboarding-plan/v0.1",
            "state": "UNHEALTHY",
            "error": _bounded_error(exc),
        }
    payload["onboarding"] = onboarding

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
