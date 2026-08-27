from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass
class SocialReceipt:
    """Secret-free receipt emitted by a social capability invocation."""

    capability: str
    credential_ref: str
    ok: bool
    started_at: str
    completed_at: str
    platform: str
    operation: str
    platform_object_id: Optional[str] = None
    permalink: Optional[str] = None
    result: Dict[str, Any] = field(default_factory=dict)
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    schema: str = "agentos.social-receipt/v0.1"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
