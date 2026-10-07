from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


MOBILE_PROFILE = "agentos.mobile-node/v0.1"
VALID_PLATFORMS = {"ios", "android"}
VALID_PRESENCE = {"enrolled", "reachable", "foreground", "background", "suspended", "revoked"}
VALID_EXECUTOR_STATES = {
    "available",
    "ready",
    "busy",
    "permission_required",
    "auth_required",
    "suspended",
    "unavailable",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class MobileExecutor:
    executor_id: str
    capabilities: tuple[str, ...]
    state: str

    def to_dict(self) -> dict[str, Any]:
        if not self.executor_id:
            raise ValueError("executor_id is required")
        if self.state not in VALID_EXECUTOR_STATES:
            raise ValueError(f"invalid mobile executor state: {self.state}")
        return {
            "executor_id": self.executor_id,
            "capabilities": list(self.capabilities),
            "state": self.state,
        }


def build_mobile_manifest(
    *,
    node_id: str,
    platform: str,
    platform_release: str,
    presence: str,
    push_provider: str,
    executors: list[MobileExecutor],
    realm_id: str = "pending",
    hostname: str | None = None,
) -> dict[str, Any]:
    node_id = str(node_id or "").strip()
    platform = str(platform or "").strip().lower()
    presence = str(presence or "").strip().lower()
    push_provider = str(push_provider or "").strip().lower()

    if not node_id:
        raise ValueError("node_id is required")
    if platform not in VALID_PLATFORMS:
        raise ValueError(f"invalid mobile platform: {platform}")
    if presence not in VALID_PRESENCE:
        raise ValueError(f"invalid mobile presence: {presence}")
    expected_push = "apns" if platform == "ios" else "fcm"
    if push_provider != expected_push:
        raise ValueError(f"{platform} mobile node requires push provider {expected_push}")

    serialized = [executor.to_dict() for executor in executors]
    capabilities = sorted({
        capability
        for executor in serialized
        if executor["state"] in {"available", "ready", "busy"}
        for capability in executor["capabilities"]
    })

    return {
        "schema": "agentos.node-manifest/v0.1",
        "realm_id": realm_id,
        "node_id": node_id,
        "role": "client",
        "hostname": hostname or node_id,
        "platform": platform,
        "platform_release": str(platform_release or "unknown"),
        "observed_at": _utc_now(),
        "capabilities": capabilities,
        "tool_presence": {},
        "surface_inventory": {
            "schema": "agentos.surface-inventory/v0.1",
            "surface_count": 0,
            "surfaces": [],
        },
        "mobile": {
            "profile": MOBILE_PROFILE,
            "transport": {
                "mode": "push-assisted",
                "provider": push_provider,
            },
            "presence": presence,
            "executors": serialized,
        },
    }


def build_mobile_heartbeat(manifest: dict[str, Any]) -> dict[str, Any]:
    if manifest.get("schema") != "agentos.node-manifest/v0.1":
        raise ValueError("invalid node manifest")
    mobile = manifest.get("mobile") if isinstance(manifest.get("mobile"), dict) else None
    if not mobile or mobile.get("profile") != MOBILE_PROFILE:
        raise ValueError("mobile profile is required")
    presence = str(mobile.get("presence") or "")
    status = "online" if presence in {"reachable", "foreground", "background"} else "offline"
    return {
        "schema": "agentos.node-heartbeat/v0.1",
        "realm_id": manifest.get("realm_id"),
        "node_id": manifest.get("node_id"),
        "role": manifest.get("role", "client"),
        "status": status,
        "observed_at": _utc_now(),
        "uptime_seconds": None,
        "capability_count": len(manifest.get("capabilities") or []),
        "surface_count": 0,
        "manifest": {**manifest, "observed_at": _utc_now()},
    }


def executor_readiness(manifest: dict[str, Any]) -> dict[str, str]:
    mobile = manifest.get("mobile") if isinstance(manifest.get("mobile"), dict) else {}
    executors = mobile.get("executors") if isinstance(mobile.get("executors"), list) else []
    return {
        str(item.get("executor_id")): str(item.get("state"))
        for item in executors
        if isinstance(item, dict) and item.get("executor_id")
    }
