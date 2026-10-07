from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

SCHEMA = "agentos.gpt-web-vision-request/v0.1"
RESPONSE_SCHEMA = "agentos.gpt-web-vision-response/v0.1"
CAPABILITIES = {"vision.document.extract", "vision.invoice.extract"}
CHATGPT_URL = "https://chatgpt.com/"

INVOICE_FIELDS = [
    "invoice_number", "invoice_date", "seller_name", "seller_tax_id",
    "buyer_name", "buyer_tax_id", "amount_before_tax", "tax_amount",
    "total_amount", "line_items", "stamp_text",
]


def _inside(workspace: Path, target: Path) -> bool:
    try:
        target.relative_to(workspace)
        return True
    except ValueError:
        return False


def validate_request(request: dict[str, Any], *, workspace: Path) -> dict[str, Any]:
    if request.get("schema") != SCHEMA:
        raise ValueError("invalid gpt-web vision request schema")
    capability = str(request.get("capability") or "")
    if capability not in CAPABILITIES:
        raise ValueError("unsupported gpt-web vision capability")
    workspace = workspace.expanduser().resolve()
    raw = str(request.get("image_path") or "").strip()
    if not raw:
        raise ValueError("image_path is required")
    candidate = Path(raw)
    path = (candidate if candidate.is_absolute() else workspace / candidate).expanduser().resolve()
    if not _inside(workspace, path):
        raise PermissionError("image_path must stay inside workspace")
    if not path.is_file():
        raise FileNotFoundError(str(path))
    payload = path.read_bytes()
    if not payload or len(payload) > 12 * 1024 * 1024:
        raise ValueError("image must be 1..12582912 bytes")
    if path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise ValueError("unsupported image type")
    return {
        "capability": capability,
        "image_path": str(path),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "bytes": len(payload),
    }


def _request_marker(image_sha256: str) -> str:
    return "agentos-gpt-web-" + image_sha256[:20]


def build_plan(request: dict[str, Any], *, workspace: Path) -> dict[str, Any]:
    checked = validate_request(request, workspace=workspace)
    request_id = str(request.get("request_id") or _request_marker(checked["sha256"])).strip()
    if not re.fullmatch(r"[A-Za-z0-9._:-]{8,128}", request_id):
        raise ValueError("invalid request_id")
    if checked["capability"] == "vision.invoice.extract":
        fields = request.get("required_fields") or INVOICE_FIELDS
        prompt = (
            "Read the attached invoice image and return ONLY one JSON object. "
            "Do not guess unreadable values; use null and list uncertain fields. "
            "Required fields: " + ", ".join(str(x) for x in fields) + ". "
            "Amounts must be numbers, line_items must be an array, and include "
            "needs_review:boolean plus uncertain_fields:string[]. "
            + 'Also include exactly "agentos_request_id":"' + request_id + '" at top level. '
            + "Return raw JSON only: no markdown fences, prose, or extra text."
        )
    else:
        prompt = (
            "Extract structured information from the attached document image. "
            'Include exactly "agentos_request_id":"' + request_id + '" at top level. '
            + "Return raw JSON only. Do not guess unreadable values."
        )

    return {
        "schema": "agentos.node-task/v0.1",
        "action": "desktop.plan.execute",
        "plan": {
            "schema": "agentos.desktop-plan/v0.1",
            "stop_on_error": True,
            "steps": [
                {"action": "desktop.open_url", "url": CHATGPT_URL},
                {"action": "desktop.wait", "seconds": 2},
                {
                    "action": "desktop.image_paste",
                    "path": checked["image_path"],
                    "sha256": checked["sha256"],
                },
                {"action": "desktop.keyboard", "operation": "paste", "text": prompt},
            ],
        },
        "gpt_web": {
            "capability": checked["capability"],
            "request_id": request_id,
            "image_sha256": checked["sha256"],
            "input_bytes": checked["bytes"],
            "response_adapter_required": True,
        },
    }


def build_harvest_task(*, session_id: str, request_id: str) -> dict[str, Any]:
    session_id = str(session_id or "").strip()
    request_id = str(request_id or "").strip()
    if not session_id:
        raise ValueError("session_id is required")
    if not re.fullmatch(r"[A-Za-z0-9._:-]{8,128}", request_id):
        raise ValueError("invalid request_id")
    return {
        "schema": "agentos.node-task/v0.1",
        "action": "agent.context.harvest",
        "provider": "gpt-web",
        "session_id": session_id,
        "payload": {
            "schema": "agentos.gpt-web-response-harvest/v0.1",
            "selector": "assistant.response_by_request_id",
            "request_id": request_id,
            "max_characters": 65536,
        },
    }


def parse_response_text(text: str, *, request_id: str) -> dict[str, Any]:
    if not isinstance(text, str):
        raise ValueError("response text must be a string")
    if not text.strip() or len(text) > 65536:
        raise ValueError("response text must contain 1..65536 characters")
    stripped = text.strip()
    if stripped.startswith("~~~") or stripped.startswith("```") or not stripped.startswith("{") or not stripped.endswith("}"):
        raise ValueError("response must be raw JSON only")
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise ValueError("response is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("response JSON must be an object")
    if str(payload.get("agentos_request_id") or "") != request_id:
        raise ValueError("response request_id mismatch")
    return payload


def parse_harvest_receipt(receipt: dict[str, Any], *, request_id: str) -> dict[str, Any]:
    if not isinstance(receipt, dict):
        raise ValueError("harvest receipt must be an object")
    if str(receipt.get("schema") or "") != "agentos.session-receipt/v0.1":
        raise ValueError("invalid harvest receipt schema")
    result = receipt.get("result")
    if not isinstance(result, dict):
        raise ValueError("harvest receipt result missing")
    if str(result.get("request_id") or "") != request_id:
        raise ValueError("harvest receipt request_id mismatch")
    payload = parse_response_text(result.get("assistant_text"), request_id=request_id)
    return {
        "schema": RESPONSE_SCHEMA,
        "request_id": request_id,
        "payload": payload,
        "source": "gpt-web",
        "session_id": receipt.get("session_id"),
        "receipt_id": receipt.get("request_id"),
    }
