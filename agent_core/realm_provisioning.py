"""Governed bootstrap for an approved CREATE request into an isolated Realm fabric.

This is a limited Realm storage + account-owner bootstrap, not permission to
manage any existing Realm, or proof of a running independent ONE executor.
"""
from __future__ import annotations

from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any

from .account_realm_onboarding import _BASE as REQUEST_ROOT, _current_identity
from .approval_broker import load_box
from .node_registry import NodeRegistry
from .realm_fabric import RealmFabricStore


DATA_ROOT = Path(os.environ.get("AGENT_DATA_ROOT", "/home/ubuntu/agent-data"))
TENANTS_ROOT = DATA_ROOT / "realms" / "managed"
_PREFIX = "realm-onboarding-"


class ProvisioningError(ValueError):
    pass


def _digest(identity: dict[str, str]) -> str:
    return hashlib.sha256(
        (identity["provider"] + "\x00" + identity["subject"]).encode("utf-8")
    ).hexdigest()


def _request(request_id: str, root: Path) -> dict[str, Any]:
    if not request_id.startswith(_PREFIX):
        raise ProvisioningError("invalid_request_id")
    prefix = request_id[len(_PREFIX):]
    if len(prefix) != 32 or any(c not in "0123456789abcdef" for c in prefix):
        raise ProvisioningError("invalid_request_id")
    matches = []
    for entry in root.glob(prefix + "*.json"):
        if not entry.is_file() or len(entry.stem) != 64:
            continue
        if any(c not in "0123456789abcdef" for c in entry.stem):
            continue
        value = json.loads(entry.read_text(encoding="utf-8"))
        if (value.get("request_id") == request_id and
                value.get("actor") == entry.stem and
                value.get("kind") == "create" and
                value.get("provider") in {"google", "github", "facebook", "line"}):
            matches.append(value)
    if len(matches) != 1:
        raise ProvisioningError("request_not_unique_or_not_create")
    return matches[0]


def _approved(request_id: str, digest: str, box: dict[str, Any]) -> None:
    matches = [
        item for item in box.get("history", [])
        if item.get("id") == request_id and
           item.get("action_type") == "realm.onboarding.request" and
           item.get("status") == "APPROVED" and
           item.get("actor") == "oauth-account:" + digest[:16] and
           isinstance(item.get("payload"), dict) and
           item["payload"].get("request_id") == request_id and
           item["payload"].get("kind") == "create"
    ]
    if len(matches) != 1:
        raise ProvisioningError("approved_create_receipt_required")
    reviewer = str(matches[0].get("resolved_by") or "")
    if (not reviewer.startswith("platform-oauth:") or
            reviewer == "platform-oauth:" + digest[:16]):
        raise ProvisioningError("independent_platform_approval_required")


def _write_once(path: Path, record: dict[str, Any]) -> None:
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        if existing != record:
            # Immutable ownership and receipt records never silently change.
            raise ProvisioningError("conflicting_existing_record")
        return
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600),
                   "w", encoding="utf-8") as fp:
        json.dump(record, fp, ensure_ascii=False, sort_keys=True)
        fp.write("\n")
        fp.flush()
        os.fsync(fp.fileno())


def _provision_impl(
    request_id: str,
    *,
    request_root: Path,
    tenants_root: Path,
    box: dict[str, Any],
) -> dict[str, Any]:
    request = _request(request_id, request_root)
    digest = request["actor"]
    _approved(request_id, digest, box)
    realm_id = "realm-u-" + digest[:24]
    tenants_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    tenant = tenants_root / realm_id
    tenant.mkdir(mode=0o700, exist_ok=True)
    lock_path = tenant / ".bootstrap.lock"
    with lock_path.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            owner_path = tenant / "owner.json"
            owner = {
                "schema": "agentos.realm-account-membership/v1",
                "realm_id": realm_id,
                "owner_digest": digest,
                "provider": request["provider"],
                "request_id": request_id,
                "role": "owner",
            }
            if owner_path.exists() and json.loads(owner_path.read_text(encoding="utf-8")) != owner:
                raise ProvisioningError("tenant_owner_conflict")
            fabric = RealmFabricStore(
                tenant / "fabric.json",
                node_registry=NodeRegistry(path=tenant / "nodes.json"),
            )
            initialized = fabric.initialize_realm(realm_id)
            if initialized.get("realm_id") != realm_id:
                raise ProvisioningError("realm_initialization_failed")
            _write_once(owner_path, owner)
            receipt = {
                "schema": "agentos.realm-bootstrap-receipt/v1",
                "request_id": request_id,
                "realm_id": realm_id,
                "owner_binding_verified": True,
                "isolated_fabric": True,
                "one_runtime_attested": False,
            }
            _write_once(tenant / "bootstrap-receipt.json", receipt)
            return {
                "ok": True, "state": "realm_initialized",
                "realm_id": realm_id, "request_id": request_id,
                "bootstrap_receipt": "agentos.realm-bootstrap-receipt/v1",
                "one_runtime_attested": False,
            }
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def provision_approved_create(
    request_id: str,
    *,
    request_root: Path = REQUEST_ROOT,
    tenants_root: Path = TENANTS_ROOT,
    box: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Idempotently initialize independent fabric and account owner binding.

    No tokens are issued and no existing Realm or live ONE process is modified.
    """
    return _provision_impl(
        request_id, request_root=request_root, tenants_root=tenants_root,
        box=box if box is not None else load_box(),
    )


def owner_realm(
    identity: dict[str, str],
    *,
    tenants_root: Path = TENANTS_ROOT,
) -> dict[str, Any] | None:
    digest = _digest(identity)
    realm_id = "realm-u-" + digest[:24]
    tenant = tenants_root / realm_id
    try:
        owner = json.loads((tenant / "owner.json").read_text(encoding="utf-8"))
        receipt = json.loads((tenant / "bootstrap-receipt.json").read_text(encoding="utf-8"))
        if (owner.get("schema") != "agentos.realm-account-membership/v1" or
                owner.get("owner_digest") != digest or
                owner.get("provider") != identity["provider"] or
                owner.get("role") != "owner" or
                owner.get("realm_id") != realm_id or
                receipt.get("schema") != "agentos.realm-bootstrap-receipt/v1" or
                receipt.get("realm_id") != realm_id or
                receipt.get("request_id") != owner.get("request_id") or
                receipt.get("isolated_fabric") is not True):
            return None
        fabric = RealmFabricStore(
            tenant / "fabric.json",
            node_registry=NodeRegistry(path=tenant / "nodes.json"),
        ).load()
        if fabric.get("realm_id") != realm_id:
            return None
        return {
            "realm_id": realm_id, "role": "owner",
            "request_id": owner["request_id"],
            "node_count": len(fabric.get("nodes", {})),
            "stage": "isolated_fabric_initialized",
            "one_runtime_attested": False,
            "bootstrap_receipt": receipt["schema"],
        }
    except (OSError, ValueError, KeyError, TypeError):
        return None


def account_virtual_one(*, host: str, cookie: str | None,
                        tenants_root: Path = TENANTS_ROOT) -> tuple[int, dict[str, Any]]:
    if host.lower().split(":")[0] != "agentos.milkcat.org":
        return 400, {"ok": False, "error": "invalid_site"}
    identity = _current_identity(host=host, cookie=cookie)
    if identity is None:
        return 401, {"ok": False, "error": "signin_required"}
    realm = owner_realm(identity, tenants_root=tenants_root)
    if realm is None:
        return 403, {"ok": False, "error": "realm_membership_required"}
    return 200, {"ok": True, **realm}


def reconcile_approved_creates(
    *, request_root: Path = REQUEST_ROOT,
    tenants_root: Path = TENANTS_ROOT,
    box: dict[str, Any] | None = None,
) -> dict[str, int]:
    """Reconcile historical authorized create approvals after a deployment."""
    decisions = box if box is not None else load_box()
    seen: set[str] = set()
    counts = {"approved_create": 0, "initialized": 0, "blocked": 0}
    for item in decisions.get("history", []):
        if (item.get("action_type") != "realm.onboarding.request" or
                item.get("status") != "APPROVED" or
                not isinstance(item.get("payload"), dict) or
                item["payload"].get("kind") != "create"):
            continue
        request_id = str(item.get("id") or "")
        if request_id in seen:
            counts["blocked"] += 1
            continue
        seen.add(request_id)
        counts["approved_create"] += 1
        try:
            provision_approved_create(
                request_id, request_root=request_root,
                tenants_root=tenants_root, box=decisions,
            )
            counts["initialized"] += 1
        except (ProvisioningError, OSError, ValueError):
            counts["blocked"] += 1
    return counts


if __name__ == "__main__":
    # Never enumerate personal account data or OAuth credentials in logs.
    result = reconcile_approved_creates()
    print(json.dumps(result, sort_keys=True))
    sys.exit(0 if result["blocked"] == 0 else 1)
