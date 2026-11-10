"""
Social Relationship Galaxy Canonical Models & Graph Algorithm
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple


WEIGHTS = {
    "follow": 10.0,
    "quote": 6.0,
    "reply": 5.0,
    "mention": 5.0,
    "repost": 4.0,
    "like": 1.0,
    "interaction": 2.0,
}


@dataclass
class CanonicalSocialEvent:
    id: str
    source: str
    actor_id: str
    actor_name: str
    target_id: str
    target_name: str
    event_type: str
    timestamp: str
    confidence: float = 1.0
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "source": self.source,
            "actor_id": self.actor_id,
            "actor_name": self.actor_name,
            "target_id": self.target_id,
            "target_name": self.target_name,
            "event_type": self.event_type,
            "timestamp": self.timestamp,
            "confidence": self.confidence,
            "meta": self.meta,
        }


class IdentityResolver:
    """跨社群同質帳號對齊推導器 (Cross-Platform Identity Resolver)。"""

    def __init__(self):
        self._bindings: Dict[str, str] = {}  # platform_id -> canonical_entity_id

    def bind(self, platform_id: str, canonical_entity_id: str):
        self._bindings[platform_id] = canonical_entity_id

    def resolve(self, platform_id: str) -> str:
        return self._bindings.get(platform_id, platform_id)

    def resolve_event(self, event: CanonicalSocialEvent) -> CanonicalSocialEvent:
        return CanonicalSocialEvent(
            id=event.id,
            source=event.source,
            actor_id=self.resolve(event.actor_id),
            actor_name=event.actor_name,
            target_id=self.resolve(event.target_id),
            target_name=event.target_name,
            event_type=event.event_type,
            timestamp=event.timestamp,
            confidence=event.confidence,
            meta=event.meta,
        )


class RelationshipGraph:
    """五級強度評級與六軸社交輪廓圖引擎。"""

    def __init__(self, self_id: str, days: int = 30):
        self.self_id = self_id
        self.days = days

    def compute(self, events: List[CanonicalSocialEvent]) -> Dict[str, Any]:
        now_ts = datetime.now(timezone.utc).timestamp()
        cutoff_ts = now_ts - self.days * 86400 if self.days else 0

        nodes_map: Dict[str, Dict[str, Any]] = {}

        for e in events:
            # 時間過濾
            try:
                dt = datetime.fromisoformat(e.timestamp.replace("Z", "+00:00"))
                e_ts = dt.timestamp()
            except Exception:
                e_ts = now_ts
            if e_ts < cutoff_ts:
                continue

            # 只計算與 self_id 相關之關係
            if e.actor_id != self.self_id and e.target_id != self.self_id:
                continue

            outbound = (e.actor_id == self.self_id)
            other_id = e.target_id if outbound else e.actor_id
            other_name = e.target_name if outbound else e.actor_name

            if other_id not in nodes_map:
                nodes_map[other_id] = {
                    "id": other_id,
                    "name": other_name,
                    "score": 0.0,
                    "inbound": 0.0,
                    "outbound": 0.0,
                    "types": {},
                    "days": set(),
                }

            r = nodes_map[other_id]
            age_days = max(0.0, (now_ts - e_ts) / 86400)
            decay = math.pow(0.5, age_days / 45.0)  # 半衰期 45 天
            base = WEIGHTS.get(e.event_type.lower(), 2.0)
            direction_factor = 0.85 if outbound else 1.0
            weight = base * direction_factor * decay * max(0.0, min(1.0, e.confidence))

            r["score"] += weight
            if outbound:
                r["outbound"] += weight
            else:
                r["inbound"] += weight

            r["types"][e.event_type] = r["types"].get(e.event_type, 0) + 1
            r["days"].add(e.timestamp[:10])

        nodes = list(nodes_map.values())
        for n in nodes:
            reciprocal = (n["inbound"] > 0 and n["outbound"] > 0)
            diversity = 1.0 + min(0.25, (len(n["days"]) - 1) * 0.025)
            n["score"] *= diversity * (1.25 if reciprocal else 1.0)
            n["reciprocal"] = reciprocal
            n["score"] = round(n["score"], 1)

        nodes.sort(key=lambda x: x["score"], reverse=True)
        max_score = nodes[0]["score"] if nodes else 1.0

        for i, n in enumerate(nodes):
            q = n["score"] / (max_score or 1.0)
            if q >= 0.72:
                n["tier"] = "S"
            elif q >= 0.50:
                n["tier"] = "A"
            elif q >= 0.30:
                n["tier"] = "B"
            elif q >= 0.15:
                n["tier"] = "C"
            else:
                n["tier"] = "D"
            n["rank"] = i + 1
            n["days"] = sorted(list(n["days"]))

        # 計算六軸輪廓
        profile = self._calculate_profile(nodes, events)

        return {
            "self_id": self.self_id,
            "days": self.days,
            "nodes": nodes,
            "profile": profile,
        }

    def _calculate_profile(self, nodes: List[Dict[str, Any]], events: List[CanonicalSocialEvent]) -> Dict[str, int]:
        if not nodes:
            return {"influence": 0, "depth": 0, "reach": 0, "reciprocity": 0, "bridge": 0, "activity": 0}

        total_score = sum(n["score"] for n in nodes)
        reciprocal_ratio = sum(1 for n in nodes if n["reciprocal"]) / len(nodes)
        top_count = max(1, math.ceil(len(nodes) * 0.2))
        top_share = sum(n["score"] for n in nodes[:top_count]) / (total_score or 1.0)

        all_types = {t for n in nodes for t in n["types"].keys()}
        active_days = {e.timestamp[:10] for e in events}

        influence = min(100, max(0, int(round((math.log1p(total_score) / math.log(80.0)) * 100))))
        depth = min(100, max(0, int(round((top_share * 0.7 + reciprocal_ratio * 0.3) * 100))))
        reach = min(100, max(0, int(round((math.log1p(len(nodes)) / math.log(45.0)) * 100))))
        reciprocity = min(100, max(0, int(round(reciprocal_ratio * 100))))
        bridge = min(100, max(0, int(round((len(all_types) / 6.0 * 0.45 + min(1.0, len(nodes) / 25.0) * 0.55) * 100))))
        activity = min(100, max(0, int(round((min(1.0, len(active_days) / min(self.days or 30, 30)) * 0.6 + min(1.0, len(events) / 80.0) * 0.4) * 100))))

        return {
            "influence": influence,
            "depth": depth,
            "reach": reach,
            "reciprocity": reciprocity,
            "bridge": bridge,
            "activity": activity,
        }
