from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

SCHEMA = "agentos.gpt-web-vision-request/v0.1"
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


def build_plan(request: dict[str, Any], *, workspace: Path) -> dict[str, Any]:
    checked = validate_request(request, workspace=workspace)
    if checked["capability"] == "vision.invoice.extract":
        fields = request.get("required_fields") or INVOICE_FIELDS
        prompt = (
            "Read the attached invoice image and return ONLY one JSON object. "
            "Do not guess unreadable values; use null and list uncertain fields. "
            "Required fields: " + ", ".join(str(x) for x in fields) + ". "
            "Amounts must be numbers, line_items must be an array, and include "
            "needs_review:boolean plus uncertain_fields:string[]."
        )
    else:
        prompt = (
            "Extract structured information from the attached document image. "
            "Return ONLY JSON. Do not guess unreadable values."
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
            "image_sha256": checked["sha256"],
            "input_bytes": checked["bytes"],
            "response_adapter_required": True,
        },
    }
