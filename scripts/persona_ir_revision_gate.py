"""Gate persona identity revisions on adopted, evidence-backed durable growth.

Pure, fail-closed policy module. Experience ledger updates are deliberately
outside this gate and must never be blocked by NO_REVISION.
"""
import json


def decide_persona_revision(current_ir, candidate_ir, growth_event=None):
    if not isinstance(current_ir, dict) or not isinstance(candidate_ir, dict):
        return {"status": "BLOCKED", "reason": "IR_INVALID", "revision_allowed": False}
    if current_ir.get("revision") is None or not isinstance(current_ir.get("revision"), int):
        return {"status": "BLOCKED", "reason": "REVISION_INVALID", "revision_allowed": False}
    if candidate_ir.get("character_id") != current_ir.get("character_id"):
        return {"status": "BLOCKED", "reason": "CHARACTER_MISMATCH", "revision_allowed": False}
    old = current_ir.get("promoted_growth")
    new = candidate_ir.get("promoted_growth")
    if not isinstance(old, list) or not isinstance(new, list):
        return {"status": "BLOCKED", "reason": "GROWTH_LIST_INVALID", "revision_allowed": False}
    def growth_refs(rows):
        return [row.get("growth_ref") for row in rows if isinstance(row, dict)]
    old_refs, new_refs = growth_refs(old), growth_refs(new)
    if len(old_refs) != len(old) or len(new_refs) != len(new) or any(not x for x in new_refs):
        return {"status": "BLOCKED", "reason": "GROWTH_REFERENCE_INVALID", "revision_allowed": False}
    if len(set(new_refs)) != len(new_refs) or new_refs[:len(old_refs)] != old_refs:
        return {"status": "BLOCKED", "reason": "GROWTH_LINEAGE_INVALID", "revision_allowed": False}
    additions = new[len(old):]
    if not additions:
        return {"status": "NO_REVISION", "reason": "EXPERIENCE_ONLY",
                "revision_allowed": False, "current_revision": current_ir["revision"]}
    if len(additions) != 1:
        return {"status": "BLOCKED", "reason": "MULTIPLE_PROMOTIONS_REQUIRE_SEPARATE_REVIEW",
                "revision_allowed": False}
    addition = additions[0]
    if not isinstance(growth_event, dict) or growth_event.get("growth_ref") != addition["growth_ref"]:
        return {"status": "BLOCKED", "reason": "EVIDENCE_MISSING", "revision_allowed": False}
    if addition.get("status") not in ("adopted", "adopted_as_interaction_policy"):
        return {"status": "BLOCKED", "reason": "NOT_ADOPTED", "revision_allowed": False}
    if growth_event.get("validation") != "PASS" or growth_event.get("governance") != "APPROVED":
        return {"status": "BLOCKED", "reason": "PROMOTION_NOT_VERIFIED", "revision_allowed": False}
    if not isinstance(growth_event.get("source_event_ids"), list) or not growth_event["source_event_ids"]:
        return {"status": "BLOCKED", "reason": "SOURCE_EVIDENCE_MISSING", "revision_allowed": False}
    if candidate_ir.get("revision") != current_ir["revision"] + 1 or candidate_ir.get("parent_ir_id") != current_ir.get("ir_id"):
        return {"status": "BLOCKED", "reason": "PARENT_REVISION_MISMATCH", "revision_allowed": False}
    if json.dumps(candidate_ir.get("current_self"), sort_keys=True, ensure_ascii=False) == json.dumps(current_ir.get("current_self"), sort_keys=True, ensure_ascii=False):
        return {"status": "BLOCKED", "reason": "NO_DURABLE_SELF_DELTA", "revision_allowed": False}
    return {"status": "REVISION_ALLOWED", "reason": "VERIFIED_DURABLE_GROWTH",
            "revision_allowed": True, "growth_ref": addition["growth_ref"],
            "current_revision": current_ir["revision"], "next_revision": candidate_ir["revision"]}
