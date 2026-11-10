#!/usr/bin/env python3
"""Fail-closed capability readiness; a logged-in text composer is not image review."""
import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
bridge = ROOT / "agentos_node/chatgpt_web_bridge.py"
manifest = ROOT / "capabilities/wardrobe_visual_review/capability-manifest.json"
tree = ast.parse(bridge.read_text(encoding="utf-8"))
functions = {n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
code = bridge.read_text(encoding="utf-8")
contract = json.loads(manifest.read_text(encoding="utf-8"))
assert contract["policy"]["semantic_backend_required_for_verified_state"] is True

# These are independent contracts, not synonyms for having a valid session.
capabilities = {
    "session_readiness": "_classify" in functions and "snapshot_sessions" in functions,
    "image_attachment": "attach_review_images" in functions,
    "bounded_submission": "submit_review_request" in functions,
    "completion_observer": "await_review_completion" in functions,
    "structured_review_receipt": "harvest_visual_review_receipt" in functions,
}
ready = all(capabilities.values())
result = {
    "schema": "agentos.wardrobe-visual-review-provider-readiness/v1",
    "provider": "chatgpt-web",
    "classification": "CONTRACT_READY_REQUIRES_LIVE_ACCEPTANCE" if ready else "IMAGE_REVIEW_NOT_IMPLEMENTED",
    "backendReady": False,  # Source-level check never implies live visual acceptance.
    "capabilities": capabilities,
}
print(json.dumps(result, ensure_ascii=False, sort_keys=True))
# Non-ready is an expected negative contract test; flag any unsupported auto-promotion.
assert not ready or "CONTRACT_READY_REQUIRES_LIVE_ACCEPTANCE" == result["classification"]
assert result["backendReady"] is False
