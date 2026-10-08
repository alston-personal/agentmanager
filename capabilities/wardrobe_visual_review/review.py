from __future__ import annotations

from typing import Any

REVIEW_REQUEST_SCHEMA = "agentos.wardrobe-visual-review-request/v1"
REVIEW_RECEIPT_SCHEMA = "agentos.wardrobe-visual-review-receipt/v1"

_TERMINAL_FAILURE_CODES = {
    "missing_selected_layer",
    "wrong_item",
    "detached_reference",
    "identity_drift",
    "gross_layer_appearance_mismatch",
}


def _normalize_checks(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    rows: list[dict[str, Any]] = []
    for raw in value:
        if not isinstance(raw, dict):
            continue
        code = str(raw.get("code") or "").strip()
        if not code:
            continue
        rows.append(
            {
                "code": code,
                "passed": bool(raw.get("passed")),
                "layer": str(raw.get("layer") or "").strip() or None,
                "message": str(raw.get("message") or "").strip() or None,
                "source": str(raw.get("source") or "machine").strip() or "machine",
            }
        )
    return rows


def evaluate_review(request: dict[str, Any]) -> dict[str, Any]:
    if request.get("schema") != REVIEW_REQUEST_SCHEMA:
        raise ValueError("unsupported wardrobe visual review request schema")

    selected = request.get("selectedLayers")
    if not isinstance(selected, dict) or not selected:
        raise ValueError("selectedLayers must be a non-empty object")

    rendered = request.get("renderedLayers")
    rendered_layers = {str(v) for v in rendered} if isinstance(rendered, list) else set()
    pending = request.get("pendingLayers")
    pending_layers = {str(v) for v in pending} if isinstance(pending, list) else set()

    checks = _normalize_checks(request.get("machineChecks"))
    semantic = request.get("semanticReceipt") if isinstance(request.get("semanticReceipt"), dict) else None

    missing = [layer for layer in selected if layer not in rendered_layers or layer in pending_layers]
    for layer in missing:
        checks.append(
            {
                "code": "missing_selected_layer",
                "passed": False,
                "layer": layer,
                "message": "Selected layer was not confirmed rendered.",
                "source": "contract",
            }
        )

    semantic_ready = bool(
        semantic
        and semantic.get("schema") == "agentos.wardrobe-visual-semantic-receipt/v1"
        and semantic.get("backendReady") is True
    )
    semantic_checks = _normalize_checks(semantic.get("checks") if semantic else None)
    checks.extend(semantic_checks)

    failed = [row for row in checks if row.get("passed") is False]
    hard_failed = [
        row for row in failed
        if str(row.get("code") or "") in _TERMINAL_FAILURE_CODES
    ]

    selected_layers = set(str(k) for k in selected.keys())
    semantic_layer_passes = {
        str(row.get("layer"))
        for row in semantic_checks
        if row.get("passed") is True and row.get("layer")
        and str(row.get("code") or "") in {"layer_match", "item_match"}
    }

    identity_ok = any(
        row.get("passed") is True and row.get("code") == "identity_preserved"
        for row in semantic_checks
    )
    no_detached_ok = any(
        row.get("passed") is True and row.get("code") == "no_detached_reference"
        for row in semantic_checks
    )

    if hard_failed:
        state = "rejected"
        accepted = False
        reason = "visual_review_failed"
    elif not semantic_ready:
        state = "candidate"
        accepted = False
        reason = "semantic_backend_not_ready"
    elif not selected_layers.issubset(semantic_layer_passes):
        state = "candidate"
        accepted = False
        reason = "semantic_layer_coverage_incomplete"
    elif not identity_ok or not no_detached_ok:
        state = "candidate"
        accepted = False
        reason = "semantic_global_checks_incomplete"
    elif failed:
        state = "rejected"
        accepted = False
        reason = "semantic_review_failed"
    else:
        state = "verified"
        accepted = True
        reason = "all_visual_checks_passed"

    return {
        "schema": REVIEW_RECEIPT_SCHEMA,
        "state": state,
        "accepted": accepted,
        "reason": reason,
        "selectedLayers": sorted(selected_layers),
        "verifiedLayers": sorted(semantic_layer_passes & selected_layers),
        "checks": checks,
        "semanticBackendReady": semantic_ready,
    }
