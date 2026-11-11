"""AgentOS-site OAuth-to-WoW account pairing. No new OAuth provider.

Browser identity is checked through existing site-scoped auth. A Bridge may
poll using a separately generated high-entropy secret; the game never receives
the secret, OAuth cookie, Node token, or execution authority.
"""
from __future__ import annotations

import hashlib
import hmac
import html
import json
import os
import re
import secrets
import time
from pathlib import Path
from typing import Any

from .account_realm_onboarding import _current_identity
from .realm_provisioning import account_virtual_one

ROOT = Path(os.environ.get("AGENT_DATA_ROOT", "/home/ubuntu/agent-data")) / "auth" / "wow-pairings"
HOST = "agentos.milkcat.org"
ORIGIN = "https://agentos.milkcat.org"
_CODE = re.compile(r"^[A-Z2-9]{12}$")
_SECRET = re.compile(r"^[a-f0-9]{64}$")
TTL = 600
SESSION_TTL = 86400


def _path(root: Path, code: str) -> Path:
    if not isinstance(code, str) or not _CODE.fullmatch(code):
        raise ValueError("invalid_code")
    return root / (code + ".json")


def _read(root: Path, code: str, now: int) -> dict[str, Any] | None:
    try:
        row = json.loads(_path(root, code).read_text(encoding="utf-8"))
        if row.get("schema") != "agentos.wow.browser-pair/v1":
            return None
        if int(row["expires"]) <= now:
            return None
        return row
    except (ValueError, KeyError, TypeError, OSError):
        return None


def _write(path: Path, row: dict[str, Any]) -> None:
    temporary = path.with_suffix(".tmp." + secrets.token_hex(6))
    try:
        with os.fdopen(os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w", encoding="utf-8") as stream:
            json.dump(row, stream, separators=(",", ":"), sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _valid_host(host: str) -> bool:
    return host.lower().split(":")[0] == HOST


def _verify_secret(row: dict[str, Any], secret: str) -> bool:
    return isinstance(secret, str) and _SECRET.fullmatch(secret) is not None and hmac.compare_digest(
        row.get("secret_sha256", ""), hashlib.sha256(secret.encode("ascii")).hexdigest()
    )


def _prune(root: Path, now: int) -> None:
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    for file in root.glob("*.json"):
        try:
            if int(json.loads(file.read_text(encoding="utf-8"))["expires"]) <= now:
                file.unlink(missing_ok=True)
        except (OSError, ValueError, KeyError, TypeError):
            continue


def start_pairing(*, host: str, root: Path = ROOT, now: int | None = None) -> tuple[int, dict[str, Any]]:
    if not _valid_host(host):
        return 400, {"ok": False, "error": "invalid_site"}
    now = int(time.time()) if now is None else now
    _prune(root, now)
    if len(list(root.glob("*.json"))) >= 256:
        return 429, {"ok": False, "error": "pairing_capacity_reached"}
    code = "".join(secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(12))
    secret = secrets.token_hex(32)
    row = {
        "schema": "agentos.wow.browser-pair/v1", "state": "pending",
        "secret_sha256": hashlib.sha256(secret.encode("ascii")).hexdigest(),
        "created": now, "expires": now + TTL,
    }
    try:
        # Exclusive write: no overwriting an outstanding code.
        with os.fdopen(os.open(_path(root, code), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w", encoding="utf-8") as stream:
            json.dump(row, stream, separators=(",", ":"))
    except FileExistsError:
        return 503, {"ok": False, "error": "pairing_collision_retry"}
    except OSError:
        return 503, {"ok": False, "error": "pairing_unavailable"}
    return 201, {"ok": True, "code": code, "claim_secret": secret,
                 "verification_url": ORIGIN + "/wow/account/authorize?code=" + code,
                 "expires_at_unix": now + TTL}


def approve_pairing(*, host: str, origin: str | None, cookie: str | None, code: str,
                    root: Path = ROOT, now: int | None = None,
                    identity_reader=None, membership_reader=None) -> tuple[int, dict[str, Any]]:
    if not _valid_host(host) or origin != ORIGIN:
        return 403, {"ok": False, "error": "invalid_origin"}
    now = int(time.time()) if now is None else now
    row = _read(root, code, now)
    if row is None or row.get("state") != "pending":
        return 410, {"ok": False, "error": "pairing_not_pending"}
    identity_reader = identity_reader or _current_identity
    membership_reader = membership_reader or account_virtual_one
    identity = identity_reader(host=host, cookie=cookie)
    if not identity:
        return 401, {"ok": False, "error": "signin_required"}
    status, membership = membership_reader(host=host, cookie=cookie)
    if status != 200 or membership.get("ok") is not True:
        return 403, {"ok": False, "error": "realm_membership_required"}
    realm = membership.get("realm_id")
    if not isinstance(realm, str) or not (realm.startswith("realm-u-") and len(realm) == 32):
        return 403, {"ok": False, "error": "unsupported_realm"}
    row["state"] = "approved"
    row["expires"] = now + SESSION_TTL
    row["account"] = str(identity.get("display_name") or "")[:128]
    row["realm"] = realm
    # Do not store OAuth cookies, passwords, provider subjects or access tokens.
    try:
        _write(_path(root, code), row)
    except OSError:
        return 503, {"ok": False, "error": "pairing_unavailable"}
    return 200, {"ok": True, "state": "approved"}


def poll_pairing(*, host: str, code: str, claim_secret: str, root: Path = ROOT,
                 now: int | None = None) -> tuple[int, dict[str, Any]]:
    if not _valid_host(host):
        return 400, {"ok": False, "error": "invalid_site"}
    now = int(time.time()) if now is None else now
    row = _read(root, code, now)
    if row is None or not _verify_secret(row, claim_secret):
        return 404, {"ok": False, "error": "pairing_not_found"}
    if row.get("state") == "pending":
        return 200, {"ok": True, "state": "pending"}
    if row.get("state") != "approved":
        return 410, {"ok": False, "error": "pairing_revoked"}
    return 200, {"ok": True, "state": "approved",
                 "account": row["account"], "realm": row["realm"]}


def revoke_pairing(*, host: str, code: str, claim_secret: str, root: Path = ROOT,
                   now: int | None = None) -> tuple[int, dict[str, Any]]:
    if not _valid_host(host):
        return 400, {"ok": False, "error": "invalid_site"}
    now = int(time.time()) if now is None else now
    row = _read(root, code, now)
    if row is None or not _verify_secret(row, claim_secret):
        return 404, {"ok": False, "error": "pairing_not_found"}
    # A revoked session must not be replayable.
    try:
        _path(root, code).unlink(missing_ok=True)
    except OSError:
        return 503, {"ok": False, "error": "revocation_unavailable"}
    return 200, {"ok": True, "state": "revoked"}


def authorization_html(*, host: str, code: str, cookie: str | None,
                       root: Path = ROOT, now: int | None = None,
                       identity_reader=None) -> tuple[int, str]:
    if not _valid_host(host):
        return 400, "Invalid AgentOS site"
    now = int(time.time()) if now is None else now
    if _read(root, code, now) is None:
        return 410, "Pairing expired. Restart from the WoW Addon."
    identity_reader = identity_reader or _current_identity
    signed_in = identity_reader(host=host, cookie=cookie)
    url = "/wow/account/authorize?code=" + code
    if not signed_in:
        signin = "/dashboard/api/auth/signin/google?site=agentos&returnTo=" + url.replace("?", "%3F").replace("=", "%3D")
        return 200, '<!doctype html><meta charset="utf-8"><h1>AgentOS WoW account pairing</h1><p>Sign in with the account you want to use in WoW.</p><a href="' + signin + '">Sign in with Google</a>'
    display = html.escape(str(signed_in.get("display_name") or "signed-in account"))
    return 200, ('<!doctype html><meta charset="utf-8"><h1>Authorize WoW account</h1>'
        '<p>Current AgentOS account: ' + display + '</p><p>Only continue if this is the intended account.</p>'
        '<button id="approve">Approve this account for WoW</button>'
        '<p><a href="/dashboard/api/auth/logout?returnTo=%2Fwelcome">Switch website account</a></p>'
        '<script>document.getElementById("approve").onclick=async()=>{'
        'const r=await fetch("/v1/wow/account/approve",{method:"POST",credentials:"same-origin",'
        'headers:{"Content-Type":"application/json"},body:JSON.stringify({code:"' + code + '"})});'
        'document.body.textContent=r.ok?"Pairing approved. Return to WoW.":"Pairing failed. Verify Realm membership and try again.";'
        '};</script>')
