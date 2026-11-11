"""Realm-scoped Node enrollment and read-only Node Map, reusing existing Fabric.

Owner APIs require verified AgentOS OAuth membership; device intake/claim
requires its own per-request claim secret and never accepts a Realm selector as
authority to approve or inspect other nodes.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any

from .account_realm_onboarding import _current_identity
from .node_registry import NodeRegistry
from .realm_fabric import RealmFabricStore
from .realm_provisioning import TENANTS_ROOT, owner_realm

HOST = "agentos.milkcat.org"
ORIGIN = "https://agentos.milkcat.org"
_REALM = re.compile(r"realm-u-[0-9a-f]{24}\Z")
_CODE = re.compile(r"[A-Z2-9]{4}-[A-Z2-9]{4}\Z")


def _store(realm_id: str, *, root: Path) -> RealmFabricStore:
    if not _REALM.fullmatch(realm_id):
        raise ValueError("invalid_realm_id")
    folder = root / realm_id
    # Never fall back to default realm-alston fabric.
    if not (folder / "owner.json").is_file() or not (folder / "bootstrap-receipt.json").is_file():
        raise ValueError("realm_not_initialized")
    store = RealmFabricStore(
        folder / "fabric.json", node_registry=NodeRegistry(path=folder / "nodes.json")
    )
    if store.load().get("realm_id") != realm_id:
        raise ValueError("realm_mismatch")
    return store


def _owner(*, host: str, cookie: str | None, root: Path):
    if host.lower().split(":")[0] != HOST:
        return 400, None, {"ok": False, "error": "invalid_site"}
    identity = _current_identity(host=host, cookie=cookie)
    if identity is None:
        return 401, None, {"ok": False, "error": "signin_required"}
    realm = owner_realm(identity, tenants_root=root)
    if realm is None:
        return 403, None, {"ok": False, "error": "realm_membership_required"}
    return 200, realm, None


def owner_node_map(*, host: str, cookie: str | None,
                   root: Path = TENANTS_ROOT) -> tuple[int, dict[str, Any]]:
    code, realm, error = _owner(host=host, cookie=cookie, root=root)
    if error:
        return code, error
    try:
        store = _store(realm["realm_id"], root=root)
        fabric = store.load()
        registry = store.node_registry.node_map()
    except (OSError, ValueError):
        return 503, {"ok": False, "error": "node_map_unavailable"}
    # Client node manifests can contain local paths and private inventory.
    # Only expose the minimal operational projection to this Realm owner.
    nodes = []
    for entry in registry.get("nodes", []):
        nodes.append({
            "node_id": entry.get("node_id"),
            "role": entry.get("role"),
            "status": entry.get("status"),
            "last_heartbeat_at": entry.get("last_heartbeat_at"),
            "capabilities": entry.get("capabilities", []),
        })
    pending = []
    now = datetime.now(timezone.utc)
    for value in fabric.get("join_requests", {}).values():
        if value.get("claimed_at") or value.get("denied_at"):
            continue
        try:
            expiry = datetime.fromisoformat(str(value.get("expires_at")).replace("Z", "+00:00"))
        except ValueError:
            continue
        if expiry < now:
            continue
        pending.append({
            "node_id": value.get("manifest", {}).get("node_id"),
            "user_code": value.get("user_code"),
            "expires_at": value.get("expires_at"),
            "approved": bool(value.get("approved_at")),
        })
    return 200, {
        "ok": True, "realm_id": realm["realm_id"],
        "node_count": len(nodes),
        "online_node_count": sum(1 for x in nodes if x.get("status") == "online"),
        "nodes": nodes, "pending_joins": pending,
        "one_runtime_attested": False,
    }


def owner_approve_code(*, host: str, cookie: str | None, origin: str | None,
                       code: str, root: Path = TENANTS_ROOT) -> tuple[int, dict[str, Any]]:
    status, realm, error = _owner(host=host, cookie=cookie, root=root)
    if error:
        return status, error
    if origin != ORIGIN:
        return 403, {"ok": False, "error": "invalid_origin"}
    selector = str(code or "").strip().upper()
    if not _CODE.fullmatch(selector):
        return 400, {"ok": False, "error": "invalid_join_code"}
    try:
        store = _store(realm["realm_id"], root=root)
        result = store.approve_join(selector)
    except (KeyError, PermissionError, ValueError, OSError):
        return 409, {"ok": False, "error": "unknown_or_expired_realm_join_code"}
    return 200, {
        "ok": True, "realm_id": realm["realm_id"],
        "node_id": result["node_id"], "user_code": result["user_code"],
        "status": "approved_pending_node_claim",
    }


def device_join(*, host: str, realm_id: str, action: str,
                body: dict[str, Any], root: Path = TENANTS_ROOT) -> tuple[int, dict[str, Any]]:
    """Device-flow endpoints, separate from an authenticated owner approval.

    A request produces a high-entropy claim secret only for the requesting
    device. Status and claim require that secret; a code alone never claims.
    """
    if host.lower().split(":")[0] != HOST:
        return 400, {"ok": False, "error": "invalid_site"}
    if action not in ("request", "status", "claim"):
        return 404, {"ok": False, "error": "not_found"}
    if not _REALM.fullmatch(realm_id):
        return 400, {"ok": False, "error": "invalid_realm_id"}
    try:
        store = _store(realm_id, root=root)
        if action == "request":
            manifest = body.get("manifest")
            if not isinstance(manifest, dict):
                return 400, {"ok": False, "error": "invalid_manifest"}
            if str(manifest.get("realm_id") or "") != realm_id:
                return 403, {"ok": False, "error": "realm_mismatch"}
            if len(str(manifest.get("node_id") or "")) > 128:
                return 400, {"ok": False, "error": "invalid_node_id"}
            result = store.request_join(manifest=manifest, expires_minutes=10)
            return 200, {"ok": True, **result}
        request_id = str(body.get("request_id") or "")
        secret = str(body.get("claim_secret") or "")
        if not re.fullmatch(r"join_[0-9a-f]{20}", request_id) or len(secret) > 256:
            return 400, {"ok": False, "error": "invalid_join_credentials"}
        if action == "status":
            result = store.join_status(request_id=request_id, claim_secret=secret)
        else:
            result = store.claim_join(request_id=request_id, claim_secret=secret)
        return 200, {"ok": True, **result}
    except PermissionError:
        return 403, {"ok": False, "error": "invalid_join_credentials"}
    except (ValueError, KeyError, OSError):
        return 409, {"ok": False, "error": "join_not_available"}
