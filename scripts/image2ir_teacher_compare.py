#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

CORE = {"head", "torso", "left_arm", "right_arm", "left_leg", "right_leg"}
PREDICTED_MAP = {"body": "torso"}


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def dump(path, obj):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def f1(tp, fp, fn):
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    score = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return precision, recall, score


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--teacher-ir", required=True)
    ap.add_argument("--probe", required=True)
    ap.add_argument("--view", default="front")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    teacher = load(args.teacher_ir)
    probe = load(args.probe)
    pred_ir = probe.get("ir") if isinstance(probe.get("ir"), dict) else {}

    teacher_parts = {
        p.get("id") for p in teacher.get("parts", [])
        if isinstance(p, dict) and p.get("id")
    }
    raw_pred_parts = set(probe.get("parts") or [])
    pred_parts = {PREDICTED_MAP.get(x, x) for x in raw_pred_parts}

    teacher_core = teacher_parts & CORE
    pred_core = pred_parts & CORE
    accepted = bool(probe.get("accepted"))
    if accepted:
        tp_set = teacher_core & pred_core
        fp_set = pred_core - teacher_core
        fn_set = teacher_core - pred_core
        precision, recall, core_f1 = f1(len(tp_set), len(fp_set), len(fn_set))
    else:
        tp_set, fp_set, fn_set = set(), set(), set(teacher_core)
        precision, recall, core_f1 = 0.0, 0.0, 0.0

    expected_coverage = "full_body" if {"left_leg", "right_leg"} <= teacher_core else "upper_body"
    predicted_coverage = pred_ir.get("observed", {}).get("pose", {}).get("coverage")
    coverage_match = accepted and predicted_coverage == expected_coverage

    noncore_predictions = sorted(pred_parts - CORE)
    assumed = pred_ir.get("assumed") or {}
    assumed_fields = sorted(assumed.keys()) if isinstance(assumed, dict) else []
    unresolved = teacher.get("unresolved") or []

    score = round(0.75 * core_f1 + 0.25 * float(coverage_match), 4) if accepted else 0.0
    report = {
        "schema": "image2ir-teacher-compare/v0.1",
        "view": args.view,
        "teacher": {
            "schema": teacher.get("schema"),
            "truth_status": teacher.get("truth_status"),
            "core_parts": sorted(teacher_core),
            "unresolved_count": len(unresolved),
        },
        "prediction": {
            "accepted": accepted,
            "status_text": probe.get("status_text"),
            "runtime_error": probe.get("runtime_error"),
            "page_errors": probe.get("page_errors") or [],
            "schema": pred_ir.get("schema"),
            "model_version": probe.get("app_version"),
            "raw_parts": sorted(raw_pred_parts),
            "normalized_core_parts": sorted(pred_core),
            "noncore_predictions": noncore_predictions,
            "assumed_fields": assumed_fields,
            "coverage": predicted_coverage,
        },
        "metrics": {
            "detector_acceptance": accepted,
            "core_true_positive": sorted(tp_set),
            "core_false_positive": sorted(fp_set),
            "core_false_negative": sorted(fn_set),
            "core_precision": round(precision, 4),
            "core_recall": round(recall, 4),
            "core_f1": round(core_f1, 4),
            "expected_coverage": expected_coverage,
            "coverage_match": bool(coverage_match),
            "baseline_score": score,
        },
        "truth_policy": {
            "detector_rejection_is_valid_zero_baseline": True,
            "noncore_predictions_are_not_automatically_hallucinations": True,
            "teacher_unresolved_fields_are_excluded_from_dense_scoring": True,
            "score_is_shared_observable_baseline_not_full_ir_equivalence": True,
        },
    }
    dump(args.out, report)
    print(json.dumps({"ok": True, "accepted": accepted, "baseline_score": score, "core_f1": round(core_f1, 4), "coverage_match": bool(coverage_match)}))


if __name__ == "__main__":
    main()
