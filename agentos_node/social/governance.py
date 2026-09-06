from __future__ import annotations

from dataclasses import dataclass, field

from .contracts import SocialRequest, WRITE_OPERATIONS


@dataclass(frozen=True)
class RuntimeWriteAcceptance:
    """Ephemeral runtime authority; never implied by credentials or capability presence."""

    acceptance_id: str
    product_id: str
    platform: str
    operations: frozenset[str]
    account_binding_ids: frozenset[str] = field(default_factory=frozenset)


class SocialWriteGate:
    """Fail closed until an exact runtime acceptance is explicitly supplied."""

    def authorize(self, request: SocialRequest, acceptance: RuntimeWriteAcceptance | None = None) -> None:
        request.validate()
        if request.operation not in WRITE_OPERATIONS:
            return
        if acceptance is None:
            raise PermissionError("social_write_not_runtime_accepted")
        if not acceptance.acceptance_id:
            raise PermissionError("social_write_acceptance_id_required")
        if acceptance.product_id != request.product_id or acceptance.platform != request.platform:
            raise PermissionError("social_write_acceptance_scope_mismatch")
        if request.operation not in acceptance.operations:
            raise PermissionError("social_write_operation_not_accepted")
        if request.account_binding_id not in acceptance.account_binding_ids:
            raise PermissionError("social_write_account_not_accepted")
        if request.write_intent_id is None:
            raise PermissionError("explicit_write_intent_required")
