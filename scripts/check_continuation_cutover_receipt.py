"""Validate evidence completeness; never treat CI success as live acceptance."""
import json
import re
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
    sha_fields = ("runtime_release_sha", "readback_execution_sha256", "readback_continuity_sha256")
    for key in sha_fields:
        value = obj.get(key)
        if isinstance(value, str) and value.strip() and not re.fullmatch(r"[a-fA-F0-9]{64}" if key.endswith("sha256") else r"[a-fA-F0-9]{40}", value):
            missing.append(key + "_invalid_format")
    if obj.get("review_approval") == "example":
        missing.append("review_approval_placeholder")
    # Syntactic validity is not trust. Explicitly refuse any claim of authenticated runtime.
    if obj.get("runtime_authenticated") is True:
        missing.append("runtime_authentication_not_verified")
    return sorted(set(missing))

def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: check_continuation_cutover_receipt.py <receipt.json>")
    obj = json.loads(Path(sys.argv[1]).read_text())
    missing = assess(obj)
    print(json.dumps({"schema": "agentos.continuation-cutover-check/v1",
                      "structurally_complete": not missing, "runtime_authenticated": False, "missing_or_invalid": missing}, indent=2))
    if missing:
        raise SystemExit(1)

if __name__ == "__main__":
    main()
