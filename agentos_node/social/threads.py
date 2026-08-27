from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional

from .contracts import SocialReceipt, utc_now
from .credentials import EnvironmentCredentialResolver


class ThreadsAPIError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class ThreadsCapability:
    """Official Threads API adapter.

    This adapter deliberately does not scrape public Threads pages. Read operations are
    attempted through the credentialed API and therefore remain subject to the account's
    Meta permissions and object visibility. A token that can publish does not imply that
    it can read arbitrary third-party posts or replies.
    """

    base_url = "https://graph.threads.net/v1.0"

    def __init__(
        self,
        credential_ref: str = "threads/default",
        resolver: Optional[EnvironmentCredentialResolver] = None,
        timeout: float = 20.0,
        publish_wait_seconds: float = 10.0,
    ) -> None:
        self.credential_ref = credential_ref
        self.resolver = resolver or EnvironmentCredentialResolver()
        self.timeout = timeout
        self.publish_wait_seconds = publish_wait_seconds

    def _token(self) -> str:
        return self.resolver.resolve(self.credential_ref)

    def _request(self, method: str, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        params = dict(params or {})
        params["access_token"] = self._token()
        url = f"{self.base_url}/{path.lstrip('/')}"
        data = None
        if method.upper() == "GET":
            url = f"{url}?{urllib.parse.urlencode(params)}"
        else:
            data = urllib.parse.urlencode(params).encode("utf-8")
        req = urllib.request.Request(url, data=data, method=method.upper())
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                payload = json.loads(raw)
            except Exception:
                payload = {"error": {"message": f"HTTP {exc.code}"}}
        except Exception as exc:
            raise ThreadsAPIError("transport_error", str(exc)) from exc

        if isinstance(payload, dict) and payload.get("error"):
            error = payload["error"] or {}
            raise ThreadsAPIError(str(error.get("code", "api_error")), str(error.get("message", "Threads API error")))
        if not isinstance(payload, dict):
            raise ThreadsAPIError("invalid_response", "Threads API returned a non-object response")
        return payload

    def _receipt(self, *, capability: str, operation: str, started: str, ok: bool,
                 platform_object_id: Optional[str] = None, permalink: Optional[str] = None,
                 result: Optional[Dict[str, Any]] = None, error: Optional[Exception] = None) -> SocialReceipt:
        code = getattr(error, "code", None) if error else None
        message = str(error)[:500] if error else None
        return SocialReceipt(
            capability=capability,
            credential_ref=self.credential_ref,
            ok=ok,
            started_at=started,
            completed_at=utc_now(),
            platform="threads",
            operation=operation,
            platform_object_id=platform_object_id,
            permalink=permalink,
            result=result or {},
            error_code=code,
            error_message=message,
        )

    def identity_read(self) -> SocialReceipt:
        started = utc_now()
        try:
            data = self._request("GET", "me", {"fields": "id,username"})
            # Intentionally return identity metadata, never the token.
            return self._receipt(
                capability="social.threads.identity.read",
                operation="identity.read",
                started=started,
                ok=True,
                platform_object_id=str(data.get("id")) if data.get("id") else None,
                result={"username": data.get("username"), "credential_present": True},
            )
        except Exception as exc:
            return self._receipt(
                capability="social.threads.identity.read",
                operation="identity.read",
                started=started,
                ok=False,
                result={"credential_present": self.resolver.present(self.credential_ref)},
                error=exc,
            )

    def post_read(self, thread_id: str) -> SocialReceipt:
        started = utc_now()
        try:
            data = self._request(
                "GET",
                thread_id,
                {"fields": "id,text,timestamp,permalink,username,media_type"},
            )
            return self._receipt(
                capability="social.threads.post.read",
                operation="post.read",
                started=started,
                ok=True,
                platform_object_id=str(data.get("id") or thread_id),
                permalink=data.get("permalink"),
                result={k: data.get(k) for k in ("text", "timestamp", "username", "media_type")},
            )
        except Exception as exc:
            return self._receipt(
                capability="social.threads.post.read",
                operation="post.read",
                started=started,
                ok=False,
                platform_object_id=thread_id,
                error=exc,
            )

    def replies_read(self, thread_id: str, limit: int = 100) -> SocialReceipt:
        started = utc_now()
        safe_limit = max(1, min(int(limit), 100))
        try:
            data = self._request(
                "GET",
                f"{thread_id}/replies",
                {"fields": "id,text,timestamp,username,permalink", "limit": safe_limit},
            )
            replies = data.get("data") if isinstance(data.get("data"), list) else []
            sanitized = [
                {k: item.get(k) for k in ("id", "text", "timestamp", "username", "permalink")}
                for item in replies if isinstance(item, dict)
            ]
            return self._receipt(
                capability="social.threads.replies.read",
                operation="replies.read",
                started=started,
                ok=True,
                platform_object_id=thread_id,
                result={"replies": sanitized, "count": len(sanitized), "paging": data.get("paging")},
            )
        except Exception as exc:
            return self._receipt(
                capability="social.threads.replies.read",
                operation="replies.read",
                started=started,
                ok=False,
                platform_object_id=thread_id,
                error=exc,
            )

    def publish(self, text: str, image_url: Optional[str] = None, reply_to_id: Optional[str] = None) -> SocialReceipt:
        started = utc_now()
        try:
            identity = self._request("GET", "me", {"fields": "id"})
            user_id = identity.get("id")
            if not user_id:
                raise ThreadsAPIError("identity_missing", "Threads account id unavailable")
            params: Dict[str, Any] = {
                "media_type": "IMAGE" if image_url else "TEXT",
                "text": text,
            }
            if image_url:
                params["image_url"] = image_url
            if reply_to_id:
                params["reply_to_id"] = reply_to_id
            container = self._request("POST", f"{user_id}/threads", params)
            creation_id = container.get("id")
            if not creation_id:
                raise ThreadsAPIError("container_missing", "Threads creation id unavailable")
            if self.publish_wait_seconds:
                time.sleep(self.publish_wait_seconds)
            published = self._request("POST", f"{user_id}/threads_publish", {"creation_id": creation_id})
            thread_id = published.get("id")
            if not thread_id:
                raise ThreadsAPIError("publish_missing", "Published thread id unavailable")
            permalink = None
            try:
                meta = self._request("GET", str(thread_id), {"fields": "permalink"})
                permalink = meta.get("permalink")
            except Exception:
                pass
            return self._receipt(
                capability="social.threads.reply" if reply_to_id else "social.threads.publish",
                operation="reply" if reply_to_id else "publish",
                started=started,
                ok=True,
                platform_object_id=str(thread_id),
                permalink=permalink,
                result={"reply_to_id": reply_to_id} if reply_to_id else {},
            )
        except Exception as exc:
            return self._receipt(
                capability="social.threads.reply" if reply_to_id else "social.threads.publish",
                operation="reply" if reply_to_id else "publish",
                started=started,
                ok=False,
                result={"reply_to_id": reply_to_id} if reply_to_id else {},
                error=exc,
            )
