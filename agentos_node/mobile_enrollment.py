from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import parse_qs, urlencode, urlparse


MOBILE_ENROLLMENT_SCHEME = "agentos"
MOBILE_ENROLLMENT_HOST = "join"
MOBILE_ENROLLMENT_VERSION = "v1"


@dataclass(frozen=True)
class MobileEnrollmentLink:
    one_url: str
    version: str = MOBILE_ENROLLMENT_VERSION

    def encode(self) -> str:
        one_url = str(self.one_url or "").strip().rstrip("/")
        if not one_url.startswith(("https://", "http://")):
            raise ValueError("ONE URL must be http(s)")
        query = urlencode({"one": one_url, "v": self.version})
        return f"{MOBILE_ENROLLMENT_SCHEME}://{MOBILE_ENROLLMENT_HOST}?{query}"

    @classmethod
    def parse(cls, value: str) -> "MobileEnrollmentLink":
        parsed = urlparse(str(value or "").strip())
        if parsed.scheme != MOBILE_ENROLLMENT_SCHEME or parsed.netloc != MOBILE_ENROLLMENT_HOST:
            raise ValueError("invalid AgentOS mobile enrollment link")
        query = parse_qs(parsed.query)
        one_url = str((query.get("one") or [""])[0]).strip().rstrip("/")
        version = str((query.get("v") or [""])[0]).strip()
        if not one_url.startswith(("https://", "http://")):
            raise ValueError("invalid ONE URL")
        if version != MOBILE_ENROLLMENT_VERSION:
            raise ValueError(f"unsupported mobile enrollment version: {version}")
        return cls(one_url=one_url, version=version)


def build_join_request_payload(manifest: dict, *, expires_minutes: int = 10) -> dict:
    if manifest.get("schema") != "agentos.node-manifest/v0.1":
        raise ValueError("canonical node manifest required")
    mobile = manifest.get("mobile")
    if not isinstance(mobile, dict) or mobile.get("profile") != "agentos.mobile-node/v0.1":
        raise ValueError("mobile node profile required")
    return {
        "manifest": manifest,
        "expires_minutes": max(1, min(int(expires_minutes), 30)),
    }
