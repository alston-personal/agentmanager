"""
Base Social Adapter Definition
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List
from ..models import CanonicalSocialEvent


class BaseSocialAdapter(ABC):
    """社群平台抽象適配器 (Abstract Social Platform Adapter)。"""

    @property
    @abstractmethod
    def platform_name(self) -> str:
        """平台名稱，如 'threads', 'x', 'bluesky', 'mastodon'。"""
        pass

    @abstractmethod
    def parse_raw_event(self, raw: Dict[str, Any]) -> CanonicalSocialEvent:
        """將平台的原始事件物件轉為標準 CanonicalSocialEvent。"""
        pass

    def parse_batch(self, raw_events: List[Dict[str, Any]]) -> List[CanonicalSocialEvent]:
        """批量解析。"""
        results = []
        for r in raw_events:
            try:
                ev = self.parse_raw_event(r)
                if ev:
                    results.append(ev)
            except Exception:
                continue
        return results
