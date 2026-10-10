from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from capabilities.ocr_memory import OCRMemoryContext, OCRMemoryStore
from services.invoice_intake.invoice_core import classify_review

BENCHMARK_SCHEMA = "agentos.ocr-growth-proof-benchmark/v1"
RECEIPT_SCHEMA = "agentos.growth-proof-receipt/v1"


def _stable_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_json(value: Any) -> str:
    return hashlib.sha256(_stable_json(value)).hexdigest()


def _norm(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().upper()


def _exact(expected: Any, actual: Any) -> bool:
    return _norm(expected) == _norm(actual)


def _review_rank(status: str) -> int:
    return {
        "extracted": 0,
        "quick_confirm": 1,
        "needs_review": 2,
        "recognition_insufficient": 3,
    }.get(str(status), 4)


def _case_metrics(
    fields: dict[str, Any],
    confidence: dict[str, float],
    expected: dict[str, Any],
    *,
    stamp_recognition: dict[str, Any] | None = None,
) -> dict[str, Any]:
    checks = {
        key: {
            "expected": expected_value,
            "actual": fields.get(key),
            "ok": _exact(expected_value, fields.get(key)),
        }
        for key, expected_value in expected.items()
    }
    review = classify_review(
        fields,
        confidence,
        stamp_recognition=stamp_recognition or {},
    )
    correct = sum(1 for item in checks.values() if item["ok"])
    total = len(checks)
    return {
        "checks": checks,
        "correct_fields": correct,
        "checked_fields": total,
        "field_accuracy": (correct / total if total else 0.0),
        "review_status": review["status"],
        "required_fields": list(review["required_fields"]),
        "confirm_fields": list(review["confirm_fields"]),
        "review_rank": _review_rank(review["status"]),
    }


def run_ocr_growth_proof(manifest: dict[str, Any], *, workdir: Path) -> dict[str, Any]:
    if manifest.get("schema") != BENCHMARK_SCHEMA:
        raise ValueError(f"expected schema {BENCHMARK_SCHEMA}")

    learning_events = list(manifest.get("learning_events") or [])
    heldout = list(manifest.get("heldout") or [])
    if not learning_events:
        raise ValueError("learning_events is required")
    if not heldout:
        raise ValueError("heldout is required")

    source_case_ids = {
        str(event.get("source_case_id") or "")
        for event in learning_events
        if str(event.get("source_case_id") or "")
    }
    leaked = [
        str(case.get("id") or "")
        for case in heldout
        if str(case.get("id") or "") in source_case_ids
    ]
    if leaked:
        raise ValueError(f"held-out leakage detected: {sorted(leaked)}")

    memory = OCRMemoryStore(workdir / "ocr-growth-proof-memory.sqlite3")
    candidate_ids: list[str] = []

    for event in learning_events:
        confirmations = max(1, int(event.get("confirmations") or 1))
        context = OCRMemoryContext.from_mapping(event.get("context"))
        for _ in range(confirmations):
            memory.remember(
                field_name=str(event["field_name"]),
                observed_value=event.get("observed_value"),
                corrected_value=event.get("corrected_value"),
                context=context,
                actor=str(event.get("actor") or "growth-proof"),
            )
        candidate_ids.append(str(event.get("candidate_id") or event.get("id") or ""))

    rows: list[dict[str, Any]] = []
    baseline_correct = experienced_correct = checked = 0
    baseline_review_rank = experienced_review_rank = 0
    reuse_hits = false_auto_corrections = regressions = known_error_recurrences = 0
    benefited_cases = 0

    for case in heldout:
        case_id = str(case.get("id") or "")
        baseline_fields = deepcopy(case.get("baseline_fields") or {})
        baseline_confidence = {
            str(k): float(v) for k, v in (case.get("baseline_confidence") or {}).items()
        }
        expected = dict(case.get("expected") or {})
        stamp = dict(case.get("stamp_recognition") or {})
        context = OCRMemoryContext.from_mapping(case.get("context"))

        before = _case_metrics(
            baseline_fields,
            baseline_confidence,
            expected,
            stamp_recognition=stamp,
        )

        experienced_fields = deepcopy(baseline_fields)
        experienced_confidence = dict(baseline_confidence)
        applied: list[dict[str, Any]] = []

        for field_name, observed in list(baseline_fields.items()):
            if observed in (None, ""):
                continue
            decision = memory.resolve(
                field_name=field_name,
                observed_value=observed,
                context=context,
            )
            if decision.decision != "auto_correct" or decision.corrected_value in (None, ""):
                continue
            reuse_hits += 1
            experienced_fields[field_name] = decision.corrected_value
            experienced_confidence[field_name] = max(
                experienced_confidence.get(field_name, 0.0),
                0.97,
            )
            expected_value = expected.get(field_name)
            correct_after = (
                field_name not in expected
                or _exact(expected_value, decision.corrected_value)
            )
            if field_name in expected and not correct_after:
                false_auto_corrections += 1
            applied.append(
                {
                    "field": field_name,
                    "observed": observed,
                    "corrected": decision.corrected_value,
                    "score": decision.score,
                    "confirmed_count": decision.confirmed_count,
                    "reason": decision.reason,
                    "correct_against_ground_truth": correct_after,
                }
            )

        after = _case_metrics(
            experienced_fields,
            experienced_confidence,
            expected,
            stamp_recognition=stamp,
        )

        case_regressions = [
            key
            for key in expected
            if before["checks"][key]["ok"] and not after["checks"][key]["ok"]
        ]
        regressions += len(case_regressions)

        case_known_recurrence = 0
        for key in expected:
            if before["checks"][key]["ok"]:
                continue
            decision = memory.resolve(
                field_name=key,
                observed_value=baseline_fields.get(key),
                context=context,
            )
            if decision.decision == "auto_correct" and not after["checks"][key]["ok"]:
                case_known_recurrence += 1
        known_error_recurrences += case_known_recurrence

        improved = (
            after["correct_fields"] > before["correct_fields"]
            or after["review_rank"] < before["review_rank"]
        )
        if improved:
            benefited_cases += 1

        baseline_correct += before["correct_fields"]
        experienced_correct += after["correct_fields"]
        checked += before["checked_fields"]
        baseline_review_rank += before["review_rank"]
        experienced_review_rank += after["review_rank"]

        rows.append(
            {
                "id": case_id,
                "baseline": before,
                "experienced": after,
                "applied": applied,
                "regressions": case_regressions,
                "known_error_recurrences": case_known_recurrence,
                "improved": improved,
            }
        )

    baseline_accuracy = baseline_correct / checked if checked else 0.0
    experienced_accuracy = experienced_correct / checked if checked else 0.0
    accuracy_uplift = experienced_accuracy - baseline_accuracy
    review_rank_reduction = baseline_review_rank - experienced_review_rank

    g3_pass = (
        benefited_cases >= 1
        and (accuracy_uplift > 0 or review_rank_reduction > 0)
        and false_auto_corrections == 0
        and regressions == 0
        and known_error_recurrences == 0
    )

    receipt = {
        "schema": RECEIPT_SCHEMA,
        "proof_id": str(manifest.get("proof_id") or f"ocr-{sha256_json(manifest)[:16]}"),
        "domain": "invoice_ocr_memory",
        "evidence_kind": "counterfactual_replay",
        "claim_scope": (
            "Validated OCR correction memory can improve later independent invoice "
            "extractions with the OCR observation held fixed."
        ),
        "candidate_ids": [x for x in candidate_ids if x],
        "source_experience": [
            str(x.get("source_case_id") or x.get("id") or "") for x in learning_events
        ],
        "heldout_case_ids": [str(x.get("id") or "") for x in heldout],
        "controlled_variables": dict(manifest.get("controlled_variables") or {}),
        "changed_variable": "validated OCR correction memory",
        "manifest_sha256": sha256_json(manifest),
        "baseline": {
            "correct_fields": baseline_correct,
            "checked_fields": checked,
            "field_accuracy": baseline_accuracy,
            "review_rank_sum": baseline_review_rank,
        },
        "experienced": {
            "correct_fields": experienced_correct,
            "checked_fields": checked,
            "field_accuracy": experienced_accuracy,
            "review_rank_sum": experienced_review_rank,
            "memory_reuse_hits": reuse_hits,
        },
        "uplift": {
            "field_accuracy_absolute": accuracy_uplift,
            "correct_fields": experienced_correct - baseline_correct,
            "review_rank_reduction": review_rank_reduction,
            "benefited_cases": benefited_cases,
        },
        "regressions": {
            "false_auto_corrections": false_auto_corrections,
            "correct_to_wrong": regressions,
            "known_error_recurrences": known_error_recurrences,
        },
        "reuse_boundary": str(manifest.get("reuse_boundary") or "independent_replay"),
        "rows": rows,
        "verdict": "G3" if g3_pass else "NOT_G3",
        "limitations": [
            "This replay isolates the cognitive delta by holding the captured OCR observation fixed.",
            "A production-strength flagship proof still requires held-out real invoice captures from a later execution.",
        ],
    }
    receipt["receipt_sha256"] = sha256_json(receipt)
    return receipt
