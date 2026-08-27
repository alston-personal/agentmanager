#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def midpoint(item: dict[str, Any]) -> tuple[float, float] | None:
    if "midpoint_px" in item:
        p = item["midpoint_px"]
        return float(p["x"]), float(p["y"])
    a, b = item.get("start_px"), item.get("end_px")
    if a and b:
        return (float(a["x"]) + float(b["x"])) / 2, (float(a["y"]) + float(b["y"])) / 2
    return None


def distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


def match(pred: list[dict[str, Any]], truth: list[dict[str, Any]], tolerance_px: float) -> tuple[int, int, int]:
    used: set[int] = set()
    tp = 0
    for p in pred:
        pm = midpoint(p)
        if pm is None:
            continue
        best_i, best_d = None, float("inf")
        for i, t in enumerate(truth):
            if i in used:
                continue
            tm = midpoint(t)
            if tm is None:
                continue
            d = distance(pm, tm)
            if d < best_d:
                best_i, best_d = i, d
        if best_i is not None and best_d <= tolerance_px:
            used.add(best_i)
            tp += 1
    return tp, max(0, len(pred) - tp), max(0, len(truth) - tp)


def metrics(tp: int, fp: int, fn: int) -> dict[str, float | int]:
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "precision": round(precision, 4), "recall": round(recall, 4), "f1": round(f1, 4)}


def score_count(pred: list[Any], truth: list[Any]) -> dict[str, int | float]:
    delta = len(pred) - len(truth)
    return {"predicted": len(pred), "truth": len(truth), "delta": delta, "absolute_error": abs(delta)}


def main() -> int:
    ap = argparse.ArgumentParser(description="Score LayoutLib semantic IR against manually annotated ground truth.")
    ap.add_argument("prediction", type=Path, help="LayoutLib Spatial IR JSON")
    ap.add_argument("ground_truth", type=Path, help="Ground-truth JSON")
    ap.add_argument("--tolerance-px", type=float, default=24.0)
    ap.add_argument("--min-door-precision", type=float, default=0.80)
    ap.add_argument("--min-door-recall", type=float, default=0.80)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    pred, truth = load(args.prediction), load(args.ground_truth)
    report: dict[str, Any] = {"schema": "layoutlib.semantic-benchmark/v1", "tolerance_px": args.tolerance_px}
    for key in ("doors", "windows"):
        tp, fp, fn = match(list(pred.get(key, [])), list(truth.get(key, [])), args.tolerance_px)
        report[key] = metrics(tp, fp, fn)
    report["rooms"] = score_count(list(pred.get("rooms", [])), list(truth.get("rooms", [])))
    report["openings"] = score_count(list(pred.get("openings", [])), list(truth.get("openings", [])))
    report["token_cost"] = pred.get("semantic_summary", {}).get("token_cost")
    d = report["doors"]
    report["mvp_gate"] = {
        "door_precision_min": args.min_door_precision,
        "door_recall_min": args.min_door_recall,
        "pass": d["precision"] >= args.min_door_precision and d["recall"] >= args.min_door_recall,
    }

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"Door P/R/F1: {d['precision']:.3f} / {d['recall']:.3f} / {d['f1']:.3f}")
        w = report["windows"]
        print(f"Window P/R/F1: {w['precision']:.3f} / {w['recall']:.3f} / {w['f1']:.3f}")
        print(f"Rooms predicted/truth: {report['rooms']['predicted']} / {report['rooms']['truth']}")
        print(f"MVP gate: {'PASS' if report['mvp_gate']['pass'] else 'FAIL'}")
    return 0 if report["mvp_gate"]["pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
