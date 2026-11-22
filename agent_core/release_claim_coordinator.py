"""Isolated release preflight/claim coordinator for a future trusted ONE adapter.

NOT an Oracle deployment entrypoint. Injection here is a security-sensitive
composition root: the caller must supply trusted authenticated readers bound to
ONE and the target runtime, never a request-supplied approval or identity.
A returned token is not a permission to execute external side effects until
the privileged Oracle writer and rollback boundary enforce it.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Mapping

from agent_core.release_authorization import verify_release_intent
from agent_core.release_epoch_store import ReleaseFenceError, TargetReleaseEpochStore


TrustedIntentReader = Callable[[Mapping[str, Any]], Mapping[str, Any] | None]
TrustedPrincipalReader = Callable[[], str | None]


def claim_from_trusted_readers(
    *,
    request: Mapping[str, Any],
    intent_reader: TrustedIntentReader,
    principal_reader: TrustedPrincipalReader,
    target_store: TargetReleaseEpochStore,
    now: datetime | None = None,
) -> str:
    """Prepare a fenced claim; never invokes Git, systemd or file writers.

    `intent_reader` and `principal_reader` are *operator provisioned* trusted
    dependencies, not callables supplied by a workflow/Executor. Production
    wiring must attest their identity/authentication and ONE origin separately.
    """
    if not callable(intent_reader) or not callable(principal_reader):
        raise ReleaseFenceError("trusted_release_adapter_missing")
    if not isinstance(request, Mapping):
        raise ReleaseFenceError("invalid_release_request")
    scope = {k: request.get(k) for k in ("repository", "realm_id", "environment")}
    if any(not isinstance(v, str) or not v for v in scope.values()):
        raise ReleaseFenceError("invalid_release_scope")

    try:
        principal = principal_reader()
        approved = intent_reader(request)
    except Exception as exc:
        raise ReleaseFenceError("trusted_release_reader_unavailable") from exc

    # The durable target's actual active epoch is never taken from Executor JSON.
    state = target_store.inspect(**scope)
    observed_target = {
        **scope, "release_epoch": state["active_epoch"],
    }
    decision = verify_release_intent(
        request=request, approved_intent=approved,
        observed_target=observed_target,
        authenticated_principal=principal,
        now=now if now is not None else datetime.now(timezone.utc),
    )
    if not decision.allowed:
        raise ReleaseFenceError(decision.reason)
    return target_store.claim(
        **scope, project_id=request["project_id"],
        operation=request["operation"], authenticated_principal=principal,
        expected_active_epoch=state["active_epoch"],
        new_epoch=decision.release_epoch,
        source_sha=request["source_commit"],
        artifact_digest=request["artifact_digest"],
        approval_receipt_id=request["approval_receipt_id"],
        decision=decision,
    )
