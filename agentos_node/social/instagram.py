from __future__ import annotations

import time
from typing import Any, Dict, Optional

from .contracts import SocialReceipt, utc_now
from .credentials import EnvironmentCredentialResolver


class InstagramAPIError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class InstagramCapability:
    base_url = "https://graph.facebook.com/v20.0"

    def __init__(self, credential_ref: str = "instagram/default", resolver=None, page_id: Optional[str] = None, ig_id: Optional[str] = None, timeout: float = 30.0, publish_wait_seconds: float = 5.0):
        self.credential_ref = credential_ref
        self.resolver = resolver or EnvironmentCredentialResolver()
        self.page_id = page_id
        self.ig_id = ig_id
        self.timeout = timeout
        self.publish_wait_seconds = publish_wait_seconds

    def _requests(self):
        try:
            import requests
            return requests
        except ImportError as exc:
            raise InstagramAPIError("dependency_missing", "requests is required for Instagram publishing") from exc

    def _token(self) -> str:
        return self.resolver.resolve(self.credential_ref)

    @staticmethod
    def _api_error(payload: Dict[str, Any], fallback: str) -> InstagramAPIError:
        error = payload.get("error") if isinstance(payload, dict) else None
        if isinstance(error, dict):
            return InstagramAPIError(str(error.get("code", "api_error")), str(error.get("message", fallback)))
        return InstagramAPIError("api_error", fallback)

    def _resolve_ig_id(self) -> str:
        if self.ig_id:
            return str(self.ig_id)
        requests = self._requests()
        token = self._token()
        if self.page_id:
            data = requests.get(f"{self.base_url}/{self.page_id}", params={"fields": "instagram_business_account", "access_token": token}, timeout=self.timeout).json()
            account = data.get("instagram_business_account") if isinstance(data, dict) else None
            if isinstance(account, dict) and account.get("id"):
                return str(account["id"])
        pages = requests.get(f"{self.base_url}/me/accounts", params={"access_token": token}, timeout=self.timeout).json()
        for page in pages.get("data", []) if isinstance(pages, dict) else []:
            if not isinstance(page, dict) or not page.get("id"):
                continue
            data = requests.get(f"{self.base_url}/{page['id']}", params={"fields": "instagram_business_account", "access_token": token}, timeout=self.timeout).json()
            account = data.get("instagram_business_account") if isinstance(data, dict) else None
            if isinstance(account, dict) and account.get("id"):
                return str(account["id"])
        raise self._api_error(pages if isinstance(pages, dict) else {}, "Instagram Business account unavailable")

    def _receipt(self, *, capability: str, operation: str, started: str, ok: bool, object_id=None, permalink=None, result=None, error=None):
        return SocialReceipt(
            capability=capability,
            credential_ref=self.credential_ref,
            ok=ok,
            started_at=started,
            completed_at=utc_now(),
            platform="instagram",
            operation=operation,
            platform_object_id=object_id,
            permalink=permalink,
            result=result or {},
            error_code=getattr(error, "code", None) if error else None,
            error_message=str(error)[:500] if error else None,
        )

    def identity_read(self) -> SocialReceipt:
        started = utc_now()
        try:
            ig_id = self._resolve_ig_id()
            data = self._requests().get(f"{self.base_url}/{ig_id}", params={"fields": "id,username", "access_token": self._token()}, timeout=self.timeout).json()
            if not data.get("id"):
                raise self._api_error(data, "Instagram identity unavailable")
            return self._receipt(capability="social.instagram.identity.read", operation="identity.read", started=started, ok=True, object_id=str(data["id"]), result={"username": data.get("username"), "credential_present": True})
        except Exception as exc:
            return self._receipt(capability="social.instagram.identity.read", operation="identity.read", started=started, ok=False, result={"credential_present": self.resolver.present(self.credential_ref)}, error=exc)

    def publish_image(self, title: str, summary: str, image_url: str) -> SocialReceipt:
        started = utc_now()
        try:
            ig_id = self._resolve_ig_id()
            token = self._token()
            requests = self._requests()
            caption = f"【{title}】\n\n{summary}\n\n#零碎證言 #連載中 #LinkInBio"
            container = requests.post(f"{self.base_url}/{ig_id}/media", data={"image_url": image_url, "caption": caption, "access_token": token}, timeout=self.timeout).json()
            creation_id = container.get("id")
            if not creation_id:
                raise self._api_error(container, "Instagram container creation failed")
            if self.publish_wait_seconds:
                time.sleep(self.publish_wait_seconds)
            published = requests.post(f"{self.base_url}/{ig_id}/media_publish", data={"creation_id": creation_id, "access_token": token}, timeout=self.timeout).json()
            media_id = published.get("id")
            if not media_id:
                raise self._api_error(published, "Instagram publish failed")
            permalink = None
            try:
                meta = requests.get(f"{self.base_url}/{media_id}", params={"fields": "permalink", "access_token": token}, timeout=self.timeout).json()
                permalink = meta.get("permalink")
            except Exception:
                pass
            return self._receipt(capability="social.instagram.publish", operation="publish", started=started, ok=True, object_id=str(media_id), permalink=permalink)
        except Exception as exc:
            return self._receipt(capability="social.instagram.publish", operation="publish", started=started, ok=False, error=exc)

    def comment(self, media_id: str, text: str) -> SocialReceipt:
        started = utc_now()
        try:
            data = self._requests().post(f"{self.base_url}/{media_id}/comments", data={"message": text, "access_token": self._token()}, timeout=self.timeout).json()
            if not data.get("id"):
                raise self._api_error(data, "Instagram comment failed")
            return self._receipt(capability="social.instagram.reply", operation="reply", started=started, ok=True, object_id=str(data["id"]), result={"parent_id": media_id})
        except Exception as exc:
            return self._receipt(capability="social.instagram.reply", operation="reply", started=started, ok=False, result={"parent_id": media_id}, error=exc)
