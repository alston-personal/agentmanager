"""Financial intake adapter contract.

The core extractor produces one vendor-neutral canonical document. ERP-specific
plugins transform that canonical payload into importable data without owning OCR,
camera capture, or accounting truth.

This keeps Winton, Excel, CSV, DingXin, etc. as replaceable adapters rather than
hard-coded branches inside the scanner.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol


CANONICAL_SCHEMA = "financial-document.normalized/v1"


@dataclass(frozen=True)
class FinancialDocument:
    document_id: str
    document_type: str
    fields: Mapping[str, Any]
    confidence: Mapping[str, float]
    source: Mapping[str, Any] = field(default_factory=dict)
    validation: Mapping[str, Any] = field(default_factory=dict)
    review_required: bool = False
    schema: str = CANONICAL_SCHEMA


@dataclass(frozen=True)
class AdapterResult:
    adapter_id: str
    payload: Any
    media_type: str
    filename: str | None = None
    warnings: tuple[str, ...] = ()
    requires_manual_import: bool = True


class AccountingAdapter(Protocol):
    adapter_id: str

    def can_export(self, document: FinancialDocument) -> bool:
        ...

    def export(self, document: FinancialDocument) -> AdapterResult:
        ...


def require_review_free(document: FinancialDocument) -> None:
    if document.review_required:
        raise ValueError("financial document still requires review")


def canonical_from_invoice_payload(payload: Mapping[str, Any]) -> FinancialDocument:
    return FinancialDocument(
        document_id=str(payload.get("invoice_id") or payload.get("document_id") or ""),
        document_type=str(payload.get("document_type") or "invoice"),
        fields=dict(payload.get("fields") or {}),
        confidence=dict(payload.get("confidence") or {}),
        source={
            "engine": payload.get("engine"),
            "sha256": payload.get("sha256"),
            "original_filename": payload.get("original_filename"),
        },
        validation=dict(payload.get("validation") or {}),
        review_required=bool(
            payload.get("review_required")
            or str(payload.get("status") or "").lower() not in {"accepted", "reviewed", "ready", "complete"}
        ),
    )
