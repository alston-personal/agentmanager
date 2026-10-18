"""Fail-closed acceptance for separately evidenced GUI For You observations."""
from scripts.persona_for_you_observation import project_for_you_snapshot

def evaluate(snapshot):
    if not isinstance(snapshot, dict):
        return {"status": "BLOCKED", "reason": "SNAPSHOT_MISSING", "write_allowed": False}
    identity = snapshot.get("identity_receipt")
    result = project_for_you_snapshot(
        account=snapshot.get("account"), page_url=snapshot.get("page_url"),
        identity_receipt=identity, read_receipt=snapshot.get("read_receipt"),
        rows=snapshot.get("rows", []))
    result["identity_gate_verified"] = bool(
        isinstance(identity, dict) and identity.get("ok") is True
        and identity.get("account") == "mio.milkcat" and identity.get("receipt_id"))
    result["write_allowed"] = False
    result["browser_navigation_performed"] = False
    return result
