"""Fail-closed GPT Web invoice receipt to existing Vision field contract.

This adapter does not invoke GPT Web, write a DB, or change provider routing.
It accepts only a verified session receipt with matching request correlation.
"""
from __future__ import annotations

import json
from typing import Any

from services.invoice_intake.vision_ocr import CORE_FIELDS, validated_fields

OPTIONAL_FIELDS = (
    "document_type", "buyer_name", "buyer_tax_id", "buyer_address",
    "seller_name", "seller_address", "seller_phone", "seller_representative",
    "tax_type", "stamp_text", "amount_before_tax", "tax_amount",
)


def from_receipt(receipt: dict[str, Any], *, request_id: str) -> dict[str, Any]:
    if not request_id or not isinstance(receipt, dict) or receipt.get("ok") is not True:
        raise ValueError("GPT_WEB_RECEIPT_NOT_VERIFIED")
    result = receipt.get("result")
    if not isinstance(result, dict) or result.get("request_id") != request_id:
        raise ValueError("GPT_WEB_CORRELATION_MISMATCH")
    text = result.get("assistant_text")
    if not isinstance(text, str) or len(text) > 65536:
        raise ValueError("GPT_WEB_INVALID_RESPONSE")
    try:
        source = json.loads(text)
    except (ValueError, TypeError) as exc:
        raise ValueError("GPT_WEB_INVALID_JSON") from exc
    if not isinstance(source, dict) or source.get("agentos_request_id") != request_id:
        raise ValueError("GPT_WEB_MODEL_CORRELATION_MISMATCH")
    if not all(key in source for key in ("invoice_number", "invoice_date", "seller_tax_id", "total_amount")):
        raise ValueError("GPT_WEB_REQUIRED_FIELDS_MISSING")

    payload = {key: source.get(key) for key in (*CORE_FIELDS, *OPTIONAL_FIELDS)}
    # CORE_FIELDS contains vendor_name; Vision uses seller_name as its alias.
    payload["seller_name"] = source.get("seller_name") or source.get("vendor_name")
    uncertain = source.get("uncertain_fields", [])
    if not isinstance(uncertain, list) or any(not isinstance(k, str) for k in uncertain):
        raise ValueError("GPT_WEB_UNCERTAINTY_INVALID")
    line_items = source.get("line_items", [])
    if not isinstance(line_items, list):
        raise ValueError("GPT_WEB_LINE_ITEMS_INVALID")
    payload["line_items"] = line_items
    payload["uncertain_fields"] = sorted(set(uncertain) | {
        key for key in (*CORE_FIELDS, "line_items")
        if (not line_items if key == "line_items" else payload.get(key) is None)
    })
    payload["needs_review"] = True
    fields, issues = validated_fields(payload)
    return {
        "provider": "gpt-web",
        "request_id": request_id,
        "payload": payload,
        "fields": fields,
        "issues": issues,
        "needs_review": True,
    }
