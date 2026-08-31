from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from .contracts import SocialReceipt, utc_now
from .credentials import EnvironmentCredentialResolver


class FacebookAPIError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class FacebookCapability:
    base_url = "https://graph.facebook.com/v20.0"

    def __init__(self, credential_ref: str = "facebook/default", resolver=None, page_id: Optional[str] = None, timeout: float = 30.0):
        self.credential_ref = credential_ref
        self.resolver = resolver or EnvironmentCredentialResolver()
        self.page_id = page_id
        self.timeout = timeout

    def _requests(self):
        try:
            import requests
            return requests
        except ImportError as exc:
            raise FacebookAPIError("dependency_missing", "requests is required for Facebook media publishing") from exc

    def _token(self) -> str:
        return self.resolver.resolve(self.credential_ref)

    @staticmethod
    def _api_error(payload: Dict[str, Any], fallback: str) -> FacebookAPIError:
        error = payload.get("error") if isinstance(payload, dict) else None
        if isinstance(error, dict):
            return FacebookAPIError(str(error.get("code", "api_error")), str(error.get("message", fallback)))
        return FacebookAPIError("api_error", fallback)

    def _page_identity(self) -> Tuple[str, str, Optional[str]]:
        requests = self._requests()
        token = self._token()
        me = requests.get(f"{self.base_url}/me", params={"fields": "id,name", "access_token": token}, timeout=self.timeout).json()
        if self.page_id and me.get("id") == self.page_id:
            return str(me["id"]), token, me.get("name")
        accounts = requests.get(f"{self.base_url}/me/accounts", params={"access_token": token}, timeout=self.timeout).json()
        for page in accounts.get("data", []) if isinstance(accounts, dict) else []:
            if not isinstance(page, dict):
                continue
            if self.page_id and str(page.get("id")) != str(self.page_id) and page.get("username") != self.page_id:
                continue
            if not self.page_id or str(page.get("id")) == str(self.page_id) or page.get("username") == self.page_id:
                if page.get("id") and page.get("access_token"):
                    return str(page["id"]), str(page["access_token"]), page.get("name")
        raise self._api_error(accounts if isinstance(accounts, dict) else {}, "Facebook Page unavailable")

    def _receipt(self, *, capability: str, operation: str, started: str, ok: bool, object_id=None, permalink=None, result=None, error=None):
        return SocialReceipt(
            capability=capability,
            credential_ref=self.credential_ref,
            ok=ok,
            started_at=started,
            completed_at=utc_now(),
            platform="facebook",
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
            page_id, _page_token, name = self._page_identity()
            return self._receipt(capability="social.facebook.identity.read", operation="identity.read", started=started, ok=True, object_id=page_id, result={"name": name, "credential_present": True})
        except Exception as exc:
            return self._receipt(capability="social.facebook.identity.read", operation="identity.read", started=started, ok=False, result={"credential_present": self.resolver.present(self.credential_ref)}, error=exc)

    def publish_photo(self, title: str, summary: str, image_path: str) -> SocialReceipt:
        started = utc_now()
        try:
            path = Path(image_path)
            if not path.is_file():
                raise FacebookAPIError("image_missing", f"image not found: {path.name}")
            page_id, page_token, _name = self._page_identity()
            requests = self._requests()
            caption = f"【最新連載】{title}\n\n{summary}\n\n#零碎證言 #Matters #懸疑小說"
            with path.open("rb") as fh:
                response = requests.post(f"{self.base_url}/{page_id}/photos", files={"source": fh}, data={"caption": caption, "access_token": page_token}, timeout=self.timeout)
            data = response.json()
            if not data.get("id"):
                raise self._api_error(data, "Facebook photo publish failed")
            object_id = str(data.get("post_id") or data["id"])
            return self._receipt(capability="social.facebook.publish", operation="publish", started=started, ok=True, object_id=object_id, result={"photo_id": data.get("id")})
        except Exception as exc:
            return self._receipt(capability="social.facebook.publish", operation="publish", started=started, ok=False, error=exc)

    def comment(self, object_id: str, text: str) -> SocialReceipt:
        started = utc_now()
        try:
            _page_id, page_token, _name = self._page_identity()
            data = self._requests().post(f"{self.base_url}/{object_id}/comments", data={"message": text, "access_token": page_token}, timeout=self.timeout).json()
            if not data.get("id"):
                raise self._api_error(data, "Facebook comment failed")
            return self._receipt(capability="social.facebook.reply", operation="reply", started=started, ok=True, object_id=str(data["id"]), result={"parent_id": object_id})
        except Exception as exc:
            return self._receipt(capability="social.facebook.reply", operation="reply", started=started, ok=False, result={"parent_id": object_id}, error=exc)
