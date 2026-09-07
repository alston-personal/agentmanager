from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Mapping


CAPABILITY_ATTESTATION_SCHEMA = 'agentos.capability-attestation/v0.1'
CAPABILITY_VERIFICATION_STATES = frozenset({'verified', 'degraded', 'unavailable', 'unknown'})
VISUAL_LOOP_CAPABILITY = 'desktop.visual-loop'
VISUAL_LOOP_PRIMITIVES = (
    'desktop.screenshot',
    'desktop.mouse',
    'desktop.keyboard',
)

_FORBIDDEN_KEYS = frozenset({
    'access_token',
    'authorization',
    'credential',
    'credentials',
    'image_base64',
    'password',
    'refresh_token',
    'secret',
    'session_cookie',
    'token',
})


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_utc(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _contains_forbidden_payload(value: Any) -> str | None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            normalized = str(key).strip().lower()
            if normalized in _FORBIDDEN_KEYS:
                return normalized
            found = _contains_forbidden_payload(nested)
            if found:
                return found
    elif isinstance(value, (list, tuple)):
        for nested in value:
            found = _contains_forbidden_payload(nested)
            if found:
                return found
    return None


def validate_capability_attestation(attestation: Mapping[str, Any]) -> dict[str, Any]:
    """Validate one sanitized live capability observation.

    Attestation is evidence of recent operability only. It deliberately carries
    no execution authorization and must never contain credentials or raw image
    payloads.
    """
    data = dict(attestation)
    if data.get('schema') != CAPABILITY_ATTESTATION_SCHEMA:
        raise ValueError('invalid capability attestation schema')

    node_id = str(data.get('node_id') or '').strip()
    capability_id = str(data.get('capability_id') or '').strip()
    state = str(data.get('verification_state') or '').strip()
    observed_at = _parse_utc(data.get('observed_at'))
    valid_until = _parse_utc(data.get('valid_until')) if data.get('valid_until') else None

    if not node_id or not capability_id:
        raise ValueError('node_id and capability_id are required')
    if state not in CAPABILITY_VERIFICATION_STATES:
        raise ValueError('invalid verification_state')
    if observed_at is None:
        raise ValueError('valid observed_at is required')
    if valid_until is not None and valid_until < observed_at:
        raise ValueError('valid_until cannot precede observed_at')
    if 'authorized' in data:
        raise ValueError('capability attestation must not carry authorization state')

    forbidden = _contains_forbidden_payload(data)
    if forbidden:
        raise ValueError(f'forbidden capability attestation field: {forbidden}')

    return data


def effective_capability_attestation(
    attestation: Mapping[str, Any],
    *,
    now: datetime | None = None,
    default_ttl_seconds: int | None = None,
) -> dict[str, Any]:
    """Project a stored attestation into current freshness-aware live state."""
    result = validate_capability_attestation(attestation)
    observed_at = _parse_utc(result.get('observed_at'))
    assert observed_at is not None
    current = (now or _utc_now()).astimezone(timezone.utc)

    if default_ttl_seconds is None:
        default_ttl_seconds = max(1, int(os.environ.get('AGENTOS_CAPABILITY_ATTESTATION_TTL_SECONDS', '300')))
    else:
        default_ttl_seconds = max(1, int(default_ttl_seconds))

    valid_until = _parse_utc(result.get('valid_until'))
    expiry = valid_until or (observed_at + timedelta(seconds=default_ttl_seconds))
    age = max(0, int((current - observed_at).total_seconds()))
    stale = current > expiry

    result['reported_verification_state'] = result['verification_state']
    result['attestation_age_seconds'] = age
    result['attestation_stale'] = stale
    result['effective_valid_until'] = expiry.replace(microsecond=0).isoformat().replace('+00:00', 'Z')
    if stale:
        result['verification_state'] = 'unknown'
        result['verification_reason'] = 'attestation_expired'
    return result


def _runtime_boundary(attestation: Mapping[str, Any]) -> tuple[str, str, str] | None:
    provider_id = str(attestation.get('provider_id') or '').strip()
    executor_id = str(attestation.get('executor_id') or '').strip()
    runtime_session_id = str(attestation.get('runtime_session_id') or '').strip()
    if not (provider_id and executor_id and runtime_session_id):
        return None
    return provider_id, executor_id, runtime_session_id


def derive_visual_loop_attestation(
    attestations: Iterable[Mapping[str, Any]],
    *,
    now: datetime | None = None,
    default_ttl_seconds: int | None = None,
) -> dict[str, Any]:
    """Derive `desktop.visual-loop` only from fresh, same-boundary primitives."""
    current = now or _utc_now()
    by_capability: dict[str, dict[str, Any]] = {}
    for raw in attestations:
        effective = effective_capability_attestation(
            raw,
            now=current,
            default_ttl_seconds=default_ttl_seconds,
        )
        capability_id = str(effective.get('capability_id') or '')
        if capability_id in VISUAL_LOOP_PRIMITIVES:
            by_capability[capability_id] = effective

    missing = [capability for capability in VISUAL_LOOP_PRIMITIVES if capability not in by_capability]
    base = {
        'schema': 'agentos.derived-capability/v0.1',
        'capability_id': VISUAL_LOOP_CAPABILITY,
        'required_capabilities': list(VISUAL_LOOP_PRIMITIVES),
    }
    if missing:
        return {
            **base,
            'verification_state': 'unknown',
            'verification_reason': 'required_attestation_missing',
            'missing_capabilities': missing,
        }

    not_verified = [
        capability
        for capability, attestation in by_capability.items()
        if attestation.get('verification_state') != 'verified'
    ]
    if not_verified:
        return {
            **base,
            'verification_state': 'unknown',
            'verification_reason': 'required_attestation_not_verified',
            'unverified_capabilities': sorted(not_verified),
        }

    boundaries = [_runtime_boundary(by_capability[capability]) for capability in VISUAL_LOOP_PRIMITIVES]
    if any(boundary is None for boundary in boundaries):
        return {
            **base,
            'verification_state': 'unknown',
            'verification_reason': 'runtime_boundary_unbound',
        }
    if len(set(boundaries)) != 1:
        return {
            **base,
            'verification_state': 'unknown',
            'verification_reason': 'runtime_boundary_mismatch',
        }

    provider_id, executor_id, runtime_session_id = boundaries[0]  # type: ignore[misc]
    observed = [
        _parse_utc(by_capability[capability].get('observed_at'))
        for capability in VISUAL_LOOP_PRIMITIVES
    ]
    observed = [value for value in observed if value is not None]
    oldest = min(observed)
    newest = max(observed)
    return {
        **base,
        'verification_state': 'verified',
        'verification_reason': 'fresh_same_runtime_boundary_primitives',
        'provider_id': provider_id,
        'executor_id': executor_id,
        'runtime_session_id': runtime_session_id,
        'observed_at': oldest.replace(microsecond=0).isoformat().replace('+00:00', 'Z'),
        'latest_component_observed_at': newest.replace(microsecond=0).isoformat().replace('+00:00', 'Z'),
        'component_capabilities': list(VISUAL_LOOP_PRIMITIVES),
    }
