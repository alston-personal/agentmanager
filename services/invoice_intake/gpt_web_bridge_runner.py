"""Opt-in, bounded GPT Web invoice bridge job for an archived InvoiceStore document.

Provider failure must not block ordinary local OCR/Gemini. This worker uses the
existing bridge request/receipt directories and never trusts model-supplied IDs
as authority to select a database row.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path

from services.invoice_intake import vision_ocr


def run_once(store, invoice_id: str, *, bridge_root: Path, timeout_seconds: int = 75) -> dict:
    root = bridge_root.expanduser().resolve(strict=True)
    sessions_path = root / "sessions.json"
    session_doc = json.loads(sessions_path.read_text(encoding="utf-8"))
    if session_doc.get("provider") != "gpt-web":
        raise ValueError("GPT_WEB_SESSION_PROVIDER_INVALID")
    sessions = [v for v in session_doc.get("sessions", [])
                if isinstance(v, dict) and v.get("ready") is True
                and str(v.get("session_id", "")).startswith("chatgpt-web:")]
    if len(sessions) != 1:
        raise ValueError("GPT_WEB_CLEAN_SESSION_UNAVAILABLE")
    with store.connect() as db:
        row = db.execute(
            """SELECT i.status,d.stored_path,d.sha256 FROM invoices i
               JOIN documents d ON i.document_id=d.id
               WHERE i.id=? AND i.deleted_at IS NULL""", (invoice_id,),
        ).fetchone()
        if row is None:
            raise KeyError(invoice_id)
        if row["status"] not in {"needs_review", "recognition_insufficient", "quick_confirm"}:
            raise ValueError("GPT_WEB_INVOICE_NOT_REVIEWABLE")
        image_path = Path(row["stored_path"]).resolve(strict=True)
        sha = row["sha256"]
    import hashlib
    if hashlib.sha256(image_path.read_bytes()).hexdigest() != sha:
        raise ValueError("GPT_WEB_SOURCE_IMAGE_MISMATCH")
    correlation_id = "invoice-" + uuid.uuid4().hex
    outer_id = "session-invoice-" + uuid.uuid4().hex
    binding = store.register_gpt_web_invoice_request(invoice_id, request_id=correlation_id)
    if binding["image_sha256"] != sha:
        raise ValueError("GPT_WEB_INVOICE_BINDING_STALE")
    prompt = (
        vision_ocr.PROMPT
        + "\nReturn JSON fields as in the invoice schema. "
        + "Include agentos_request_id exactly: " + correlation_id
        + ". Preserve null for absent fields. "
        + "Include line_items, needs_review and uncertain_fields."
    )
    request = {
        "schema": "agentos.session-request/v0.1",
        "request_id": outer_id,
        "provider": "gpt-web",
        "operation": "invoke",
        "session_id": sessions[0]["session_id"],
        "payload": {
            "schema": "agentos.gpt-web-vision-invoke/v0.1",
            "request_id": correlation_id,
            "capability": "vision.invoice.extract",
            "image_path": str(image_path),
            "prompt": prompt,
        },
    }
    queue = root / "requests"
    if queue.is_symlink():
        raise ValueError("GPT_WEB_REQUEST_QUEUE_SYMLINK")
    queue.mkdir(parents=True, exist_ok=True)
    target = queue / (outer_id + ".json")
    tmp = queue / (outer_id + ".tmp")
    try:
        with tmp.open("x", encoding="utf-8") as fp:
            json.dump(request, fp, ensure_ascii=False)
        os.replace(tmp, target)
    finally:
        tmp.unlink(missing_ok=True)
    deadline = time.monotonic() + max(1, min(120, int(timeout_seconds)))
    while time.monotonic() < deadline:
        try:
            return store.consume_gpt_web_invoice_receipt(
                invoice_id, request_id=correlation_id,
                outer_request_id=outer_id, bridge_root=root,
            )
        except FileNotFoundError:
            time.sleep(0.5)
    raise TimeoutError("GPT_WEB_RECEIPT_TIMEOUT")
