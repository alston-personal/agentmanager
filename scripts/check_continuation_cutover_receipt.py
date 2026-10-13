"""Validate evidence completeness; never treat CI success as live acceptance."""
import json
import sys
from pathlib import Path

FIELDS = ("pr", "runtime_release_sha", "dispatch_actor", "action_receipt_id",
          "pre_generation", "post_generation", "readback_execution_sha256",
          "readback_continuity_sha256", "stale_rejection_receipt_id",
          "unguarded_rejection_receipt_id", "rollback_owner", "review_approval")

def assess(obj):
    missing = [key for key in FIELDS if not isinstance(obj.get(key), str) or not obj[key].strip()]
    if obj.get("pr") != "1923":
        missing.append("pr_must_equal_1923")
    if obj.get("pre_generation") == obj.get("post_generation") and obj.get("pre_generation"):
        missing.append("generation_must_advance")
    return sorted(set(missing))

def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: check_continuation_cutover_receipt.py <receipt.json>")
    obj = json.loads(Path(sys.argv[1]).read_text())
    missing = assess(obj)
    print(json.dumps({"schema": "agentos.continuation-cutover-check/v1",
                      "accepted": not missing, "missing_or_invalid": missing}, indent=2))
    if missing:
        raise SystemExit(1)

if __name__ == "__main__":
    main()
