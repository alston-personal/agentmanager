from __future__ import annotations

import json
import os
import stat
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


RECEIPT_SCHEMA = "agentos.social.publish-receipt/v0.1"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class SocialCapabilityError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class Credential:
    ref: str
    platform: str
    values: Mapping[str, str]

    def require(self, name: str) -> str:
        value = str(self.values.get(name) or "").strip()
        if not value:
            raise SocialCapabilityError("credential_incomplete", f"credential {self.ref!r} has no {name}")
        return value


class CredentialStore:
    """Executor-local credential references.

    The file is never returned to callers. On POSIX, group/world-readable stores are
    rejected so a reusable capability does not silently widen secret exposure.
    """

    def __init__(self, path: Path | None = None):
        self.path = path or Path(
            os.environ.get("AGENTOS_SOCIAL_CREDENTIAL_STORE")
            or Path.home() / ".agentos" / "social-credentials.json"
        )

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            raise SocialCapabilityError("credential_store_missing", f"credential store not found: {self.path}")
        if os.name == "posix":
            mode = stat.S_IMODE(self.path.stat().st_mode)
            if mode & 0o077:
                raise SocialCapabilityError("credential_store_permissions", "credential store must not be group/world readable")
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SocialCapabilityError("credential_store_invalid", str(exc)) from exc
        if not isinstance(data, dict):
            raise SocialCapabilityError("credential_store_invalid", "credential store root must be an object")
        return data

    def resolve(self, ref: str, platform: str) -> Credential:
        raw = self._load().get(ref)
        if not isinstance(raw, dict):
            raise SocialCapabilityError("credential_not_found", f"credential reference not found: {ref}")
        declared = str(raw.get("platform") or platform).lower()
        if declared != platform.lower():
            raise SocialCapabilityError("credential_platform_mismatch", f"credential {ref!r} belongs to {declared}")
        values = {str(k): str(v) for k, v in raw.items() if k != "platform" and v is not None}
        return Credential(ref=ref, platform=declared, values=values)


class HttpTransport:
    def request(self, method: str, url: str, *, params: Mapping[str, Any] | None = None) -> dict[str, Any]:
        encoded = urllib.parse.urlencode({k: v for k, v in (params or {}).items() if v is not None})
        if method.upper() == "GET":
            target = url + (("&" if "?" in url else "?") + encoded if encoded else "")
            req = urllib.request.Request(target, method="GET")
        else:
            req = urllib.request.Request(url, data=encoded.encode("utf-8"), method=method.upper())
            req.add_header("Content-Type", "application/x-www-form-urlencoded")
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                payload = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise SocialCapabilityError("platform_http_error", f"HTTP {exc.code}: {body[:1000]}") from exc
        except urllib.error.URLError as exc:
            raise SocialCapabilityError("platform_transport_error", str(exc.reason)) from exc
        try:
            data = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise SocialCapabilityError("platform_invalid_response", payload[:1000]) from exc
        if isinstance(data, dict) and data.get("error"):
            raise SocialCapabilityError("platform_error", json.dumps(data["error"], ensure_ascii=False)[:1000])
        if not isinstance(data, dict):
            raise SocialCapabilityError("platform_invalid_response", "platform response must be an object")
        return data


class SocialCapability:
    def __init__(self, store: CredentialStore | None = None, transport: HttpTransport | None = None):
        self.store = store or CredentialStore()
        self.transport = transport or HttpTransport()

    def _receipt(
        self,
        *,
        platform: str,
        operation: str,
        credential_ref: str,
        ok: bool,
        platform_object_id: str | None = None,
        permalink: str | None = None,
        result: Mapping[str, Any] | None = None,
        error: SocialCapabilityError | None = None,
    ) -> dict[str, Any]:
        receipt: dict[str, Any] = {
            "schema": RECEIPT_SCHEMA,
            "ok": ok,
            "platform": platform,
            "operation": operation,
            "credential_ref": credential_ref,
            "observed_at": _utc_now(),
        }
        if platform_object_id:
            receipt["platform_object_id"] = platform_object_id
        if permalink:
            receipt["permalink"] = permalink
        if result:
            # Only caller-safe identity/operation metadata belongs here. Never merge
            # raw credential or request dictionaries into receipts.
            receipt["result"] = dict(result)
        if error:
            receipt["error_code"] = error.code
            receipt["error_message"] = error.message
        return receipt

    def execute(self, platform: str, operation: str, credential_ref: str, args: Mapping[str, Any]) -> dict[str, Any]:
        platform = platform.lower()
        operation = operation.lower()
        try:
            credential = self.store.resolve(credential_ref, platform)
            if operation in {"publish", "reply"} and not bool(args.get("allow_write")):
                raise SocialCapabilityError("write_not_approved", "write operation requires --allow-write")
            if platform == "threads":
                return self._threads(operation, credential, args)
            if platform == "facebook":
                return self._facebook(operation, credential, args)
            if platform == "instagram":
                return self._instagram(operation, credential, args)
            raise SocialCapabilityError("unsupported_platform", platform)
        except SocialCapabilityError as exc:
            return self._receipt(
                platform=platform,
                operation=operation,
                credential_ref=credential_ref,
                ok=False,
                error=exc,
            )

    def _threads(self, operation: str, cred: Credential, args: Mapping[str, Any]) -> dict[str, Any]:
        base = "https://graph.threads.net/v1.0"
        token = cred.require("access_token")
        if operation == "identity":
            data = self.transport.request("GET", f"{base}/me", params={"fields": "id,username", "access_token": token})
            uid = str(data.get("id") or "")
            if not uid:
                raise SocialCapabilityError("identity_unverified", "Threads identity response has no id")
            return self._receipt(platform="threads", operation=operation, credential_ref=cred.ref, ok=True,
                                 platform_object_id=uid, result={"username": data.get("username")})

        text = str(args.get("text") or "")
        if not text:
            raise SocialCapabilityError("invalid_request", "text is required")
        identity = self.transport.request("GET", f"{base}/me", params={"fields": "id", "access_token": token})
        uid = str(identity.get("id") or "")
        if not uid:
            raise SocialCapabilityError("identity_unverified", "Threads identity response has no id")
        payload: dict[str, Any] = {
            "media_type": "IMAGE" if args.get("image_url") else "TEXT",
            "text": text,
            "access_token": token,
        }
        if args.get("image_url"):
            payload["image_url"] = str(args["image_url"])
        if operation == "reply":
            reply_to = str(args.get("reply_to") or "")
            if not reply_to:
                raise SocialCapabilityError("invalid_request", "reply operation requires --reply-to")
            payload["reply_to_id"] = reply_to
        elif operation != "publish":
            raise SocialCapabilityError("unsupported_operation", operation)
        container = self.transport.request("POST", f"{base}/{uid}/threads", params=payload)
        creation_id = str(container.get("id") or "")
        if not creation_id:
            raise SocialCapabilityError("publish_container_failed", "Threads did not return creation id")
        published = self.transport.request("POST", f"{base}/{uid}/threads_publish", params={"creation_id": creation_id, "access_token": token})
        object_id = str(published.get("id") or "")
        if not object_id:
            raise SocialCapabilityError("publish_failed", "Threads did not return published id")
        permalink: str | None = None
        try:
            item = self.transport.request("GET", f"{base}/{object_id}", params={"fields": "permalink", "access_token": token})
            permalink = str(item.get("permalink") or "") or None
        except SocialCapabilityError:
            pass
        return self._receipt(platform="threads", operation=operation, credential_ref=cred.ref, ok=True,
                             platform_object_id=object_id, permalink=permalink)

    def _facebook(self, operation: str, cred: Credential, args: Mapping[str, Any]) -> dict[str, Any]:
        token = cred.require("access_token")
        page_id = str(args.get("page_id") or cred.values.get("page_id") or "")
        if operation != "identity":
            raise SocialCapabilityError("operation_not_yet_verified", "Facebook write path is not enabled until controlled-publish verification")
        target = page_id or "me"
        data = self.transport.request("GET", f"https://graph.facebook.com/v23.0/{target}", params={"fields": "id,name", "access_token": token})
        object_id = str(data.get("id") or "")
        if not object_id:
            raise SocialCapabilityError("identity_unverified", "Facebook identity response has no id")
        return self._receipt(platform="facebook", operation=operation, credential_ref=cred.ref, ok=True,
                             platform_object_id=object_id, result={"name": data.get("name")})

    def _instagram(self, operation: str, cred: Credential, args: Mapping[str, Any]) -> dict[str, Any]:
        token = cred.require("access_token")
        ig_id = str(args.get("ig_id") or cred.values.get("ig_id") or "")
        if operation != "identity":
            raise SocialCapabilityError("operation_not_yet_verified", "Instagram write path is not enabled until controlled-publish verification")
        if not ig_id:
            raise SocialCapabilityError("invalid_request", "Instagram identity requires ig_id in args or credential metadata")
        data = self.transport.request("GET", f"https://graph.facebook.com/v23.0/{ig_id}", params={"fields": "id,username", "access_token": token})
        object_id = str(data.get("id") or "")
        if not object_id:
            raise SocialCapabilityError("identity_unverified", "Instagram identity response has no id")
        return self._receipt(platform="instagram", operation=operation, credential_ref=cred.ref, ok=True,
                             platform_object_id=object_id, result={"username": data.get("username")})
