"""Classify social receipts after persistence, without replaying pending writes."""
import json
import sys

ALLOWED = {"EXECUTED", "BLOCKED", "AWAITING_READBACK",
           "WRITE_OUTCOME_UNKNOWN", "RECONCILIATION_PENDING", "RECONCILED"}


def classify(receipt):
    if not isinstance(receipt, dict) or receipt.get("status") not in ALLOWED:
        raise ValueError("unexpected social executor receipt status")
    status = receipt["status"]
    if status in {"AWAITING_READBACK", "RECONCILIATION_PENDING"}:
        return "PENDING_READBACK"
    if status == "WRITE_OUTCOME_UNKNOWN":
        return "WRITE_OUTCOME_UNKNOWN"
    if status == "RECONCILED":
        return "PASS" if receipt.get("delivery_confirmed") is True else "BLOCKED"
    return "PASS" if receipt.get("ok") is True else "BLOCKED"


def main():
    receipt = json.load(open(sys.argv[1], encoding="utf-8"))
    print("persona_social_action_runtime=" + classify(receipt))
    print("persona_social_action_capability=" + str(receipt.get("capability") or "unknown"))
    write = receipt.get("write_performed")
    print("persona_social_action_write=" + ("unknown" if write is None else str(bool(write)).lower()))
    print("persona_growth_metrics_status=" + sys.argv[2])
    print("persona_growth_metrics_changed=" + sys.argv[3])


if __name__ == "__main__":
    main()
