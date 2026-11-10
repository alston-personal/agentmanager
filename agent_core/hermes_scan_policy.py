"""Hermes scan planning. Pure decision logic; never creates a scheduler or an authority grant."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

MIN_INTERVAL_HOURS = 1
MAX_INTERVAL_HOURS = 168

@dataclass(frozen=True)
class ScanSignals:
    unresolved_critical_blocker: bool = False
    meaningful_findings: int = 0
    consecutive_empty_scans: int = 0
    external_event: bool = False
    provider_available: bool = True
    resource_pressure: bool = False
    budget_remaining: bool = True

@dataclass(frozen=True)
class ScanPlan:
    interval_hours: int
    next_eligible_at: str
    reason: str
    should_run: bool


def propose_scan(*, now: datetime, last_scan_at: datetime | None, signals: ScanSignals) -> ScanPlan:
    """Return a bounded advisory schedule; the existing Scheduler/ONE owns dispatch.

    All timestamps UTC, no implicit privilege escalation or busy loop.
    External events can accelerate the *eligible time*, but never bypass authority.
    """
    if now.tzinfo is None or (last_scan_at is not None and last_scan_at.tzinfo is None):
        raise ValueError("timezone_aware_timestamps_required")
    now = now.astimezone(timezone.utc)
    if last_scan_at is not None:
        last_scan_at = last_scan_at.astimezone(timezone.utc)
        if last_scan_at > now:
            raise ValueError("future_last_scan_at")
    if signals.meaningful_findings < 0 or signals.consecutive_empty_scans < 0:
        raise ValueError("negative_scan_signal")
    if not signals.budget_remaining:
        hours, reason = 168, "budget_exhausted"
    elif signals.resource_pressure or not signals.provider_available:
        hours, reason = 72, "runtime_degraded"
    elif signals.unresolved_critical_blocker:
        hours, reason = 3, "critical_gap"
    elif signals.external_event:
        hours, reason = 1, "upstream_event"
    elif signals.meaningful_findings >= 2:
        hours, reason = 12, "high_signal"
    elif signals.consecutive_empty_scans >= 7:
        hours, reason = 168, "seven_empty_scans"
    elif signals.consecutive_empty_scans >= 3:
        hours, reason = 72, "three_empty_scans"
    else:
        hours, reason = 24, "baseline"
    hours = max(MIN_INTERVAL_HOURS, min(hours, MAX_INTERVAL_HOURS))
    next_time = now if last_scan_at is None else last_scan_at + timedelta(hours=hours)
    should_run = bool(signals.budget_remaining and signals.provider_available
                      and not signals.resource_pressure and now >= next_time)
    return ScanPlan(hours, next_time.isoformat(), reason, should_run)


def plan_after_completed_scan(*, completed_at: datetime, signals: ScanSignals) -> ScanPlan:
    """Use exactly one UTC observation for an already completed scan.

    A second clock read would make last_scan_at later than now, fail closed,
    and strand a claimed Employee lease without a terminal receipt.
    """
    return propose_scan(now=completed_at, last_scan_at=completed_at, signals=signals)
