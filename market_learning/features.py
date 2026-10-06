from __future__ import annotations

from dataclasses import dataclass
from math import log
from typing import Any, Mapping, Sequence

from .replay import ReplaySnapshot


def _clamp(value: float, low: float = -1.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


@dataclass(frozen=True)
class FeatureFrame:
    values: Mapping[str, float]
    available: tuple[str, ...]
    missing: tuple[str, ...]
    schema: str = "agentos.market-feature-frame/v1"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "values": dict(self.values),
            "available": list(self.available),
            "missing": list(self.missing),
        }


BAR_FEATURES = ("price_action", "volume", "market_regime")
KNOWN_FEATURES = (
    "price_action",
    "volume",
    "foreign_flow",
    "margin",
    "ownership_distribution",
    "market_regime",
)


def bar_feature_frame(snapshot: ReplaySnapshot) -> FeatureFrame:
    rows = list(snapshot.rows)
    closes = [float(row["close"]) for row in rows if row.get("close") is not None]
    if not closes:
        raise ValueError("feature engine requires close prices")

    # Price action: bounded log return over the last up-to-5 observations.
    price_lookback = closes[-5:]
    if len(price_lookback) >= 2 and price_lookback[0] > 0 and price_lookback[-1] > 0:
        raw_return = log(price_lookback[-1] / price_lookback[0])
        price_action = _clamp(raw_return / 0.10)
    else:
        price_action = 0.0

    # Volume: relative recent volume versus available history. 0 means neutral,
    # positive means expansion, negative contraction. Missing volume stays absent.
    volumes = [
        float(row["trade_volume"])
        for row in rows
        if row.get("trade_volume") not in (None, 0)
    ]
    values: dict[str, float] = {"price_action": price_action}
    available = {"price_action"}

    if len(volumes) >= 2:
        baseline_values = volumes[-20:-1] or volumes[:-1]
        baseline = sum(baseline_values) / len(baseline_values)
        if baseline > 0:
            ratio = volumes[-1] / baseline
            values["volume"] = _clamp(log(ratio) / log(3.0))
            available.add("volume")

    # Market regime is intentionally bar-only in v0.1: sign and persistence of
    # the recent return. Cross-sectional/index context will replace this later.
    regime_lookback = closes[-10:]
    if len(regime_lookback) >= 3 and regime_lookback[0] > 0:
        regime_return = (regime_lookback[-1] / regime_lookback[0]) - 1.0
        values["market_regime"] = _clamp(regime_return / 0.15)
        available.add("market_regime")

    # Foreign flow: recent foreign institutional net shares relative to traded
    # volume. This remains replay-safe because only signal values already merged
    # into visible EOD rows can participate.
    flow_pairs = [
        (float(row["foreign_net"]), float(row["trade_volume"]))
        for row in rows[-5:]
        if row.get("foreign_net") is not None and row.get("trade_volume") not in (None, 0)
    ]
    if flow_pairs:
        net = sum(pair[0] for pair in flow_pairs)
        volume = sum(abs(pair[1]) for pair in flow_pairs)
        if volume > 0:
            values["foreign_flow"] = _clamp((net / volume) / 0.20)
            available.add("foreign_flow")

    missing = tuple(sorted(set(KNOWN_FEATURES) - available))
    return FeatureFrame(
        values=values,
        available=tuple(sorted(available)),
        missing=missing,
    )


def bar_feature_provider(snapshot: ReplaySnapshot) -> Mapping[str, float]:
    return bar_feature_frame(snapshot).values
