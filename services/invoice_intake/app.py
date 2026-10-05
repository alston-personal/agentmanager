from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from services.invoice_intake.invoice_core import InvoiceStore
from capabilities.financial_intake import WintonExcelAdapter, canonical_from_invoice_payload

VERSION = "0.6.0"
DATA_ROOT = Path(os.environ.get("INVOICE_DATA_ROOT", "/home/ubuntu/agent-data/invoice-intake"))
MAX_UPLOAD = 12 * 1024 * 1024
DASHBOARD_SESSION = os.environ.get("DASHBOARD_SESSION_URL", "http://127.0.0.1:3000/dashboard/api/auth/session")

DATA_SCOPE = os.environ.get("INVOICE_DATA_SCOPE", "production")
store = InvoiceStore(DATA_ROOT, data_scope=DATA_SCOPE)
app = FastAPI(title="Milkcat Invoice Intake", version=VERSION)


def session_from_cookie(cookie: str | None) -> dict:
    if not cookie:
        return {"loggedIn": False}
    req = urllib.request.Request(DASHBOARD_SESSION, headers={"Cookie": cookie, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=4) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception:
        return {"loggedIn": False}


def require_user(request: Request) -> dict:
    session = session_from_cookie(request.headers.get("cookie"))
    if not session.get("loggedIn"):
        raise HTTPException(status_code=401, detail="milkcat_login_required")
    return session


class ReviewBody(BaseModel):
    fields: dict


class WintonBatchBody(BaseModel):
    invoice_ids: list[str]


@app.get("/healthz")
def healthz():
    return {"ok": True, "service": "invoice-intake", "version": VERSION}


@app.get("/v1/status")
def status(request: Request):
    session = session_from_cookie(request.headers.get("cookie"))
    return {
        "ok": True,
        "service": "invoice-intake",
        "version": VERSION,
        "ocr_engine": "rapidocr-template-v1+tesseract-fallback",
        "authenticated": bool(session.get("loggedIn")),
        "role": session.get("role") if session.get("loggedIn") else None,
        "continuous_scan": True,
        "immutable_originals": True,
        "database": "sqlite",
        "data_scope": DATA_SCOPE,
        "batch_tracking": True,
        "source_tracking": True,
    }


@app.post("/v1/ingest")
async def ingest(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    source_type: str = Form("unknown"),
    batch_id: str | None = Form(None),
):
    require_user(request)
    mime = (file.content_type or "").lower()
    if mime not in {"image/jpeg", "image/png", "image/webp"}:
        raise HTTPException(status_code=415, detail="supported_image_required")
    data = await file.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        raise HTTPException(status_code=413, detail="image_too_large")
    if not data:
        raise HTTPException(status_code=400, detail="empty_image")
    try:
        payload = store.ingest(
            data,
            file.filename or "camera.jpg",
            mime,
            source_type=source_type,
            batch_id=batch_id,
        )
        if not payload.get("duplicate") and payload.get("status") == "processing":
            background_tasks.add_task(store.process, payload["invoice_id"])
        return payload
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"invoice_ingest_failed:{type(exc).__name__}") from exc


@app.get("/v1/invoices/{invoice_id}")
def get_invoice(invoice_id: str, request: Request):
    require_user(request)
    try:
        return store.get_invoice(invoice_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="invoice_not_found")


@app.get("/v1/recent")
def recent(request: Request, limit: int = 30):
    require_user(request)
    return {"ok": True, "items": store.recent(limit)}


@app.get("/v1/invoices/{invoice_id}/original")
def get_original(invoice_id: str, request: Request):
    require_user(request)
    try:
        original = store.get_original(invoice_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="invoice_not_found")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="original_not_found")
    except ValueError:
        raise HTTPException(status_code=500, detail="original_store_integrity_error")

    response = FileResponse(
        path=original["path"],
        media_type=original["mime_type"],
        filename=original["original_filename"],
        content_disposition_type="inline",
    )
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Invoice-SHA256"] = original["sha256"]
    return response


@app.post("/v1/invoices/{invoice_id}/review")
def review(invoice_id: str, body: ReviewBody, request: Request):
    session = require_user(request)
    actor = str(session.get("username") or session.get("subject") or "milkcat-user")
    try:
        result = store.review(invoice_id, actor, body.fields)
    except KeyError:
        raise HTTPException(status_code=404, detail="invoice_not_found")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return {"ok": True, "invoice": result}


@app.get("/v1/invoices/{invoice_id}/export/winton")
def export_winton(invoice_id: str, request: Request):
    """Export one reviewed invoice through the Winton accounting adapter."""
    require_user(request)
    try:
        payload = store.get_invoice(invoice_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="invoice_not_found")

    document = canonical_from_invoice_payload(payload)
    adapter = WintonExcelAdapter()
    if not adapter.can_export(document):
        raise HTTPException(status_code=409, detail="invoice_review_required_before_export")
    try:
        result = adapter.export(document)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    headers = {
        "Content-Disposition": f'attachment; filename="{result.filename or "winton-import.csv"}"',
        "X-Accounting-Adapter": result.adapter_id,
        "X-Manual-Import-Required": "true" if result.requires_manual_import else "false",
    }
    if result.warnings:
        headers["X-Adapter-Warning"] = result.warnings[0]
    return Response(content=result.payload, media_type=result.media_type, headers=headers)


@app.post("/v1/export/winton")
def export_winton_batch(body: WintonBatchBody, request: Request):
    """Export multiple completed invoices as one Winton interchange CSV."""
    require_user(request)
    invoice_ids = [str(x).strip() for x in body.invoice_ids if str(x).strip()]
    if not invoice_ids:
        raise HTTPException(status_code=422, detail="invoice_ids_required")
    if len(invoice_ids) > 500:
        raise HTTPException(status_code=422, detail="too_many_invoices")

    documents = []
    missing = []
    for invoice_id in invoice_ids:
        try:
            payload = store.get_invoice(invoice_id)
        except KeyError:
            missing.append(invoice_id)
            continue
        documents.append(canonical_from_invoice_payload(payload))

    if missing:
        raise HTTPException(status_code=404, detail={"missing_invoice_ids": missing})

    adapter = WintonExcelAdapter()
    blocked = [
        document.document_id
        for document in documents
        if not adapter.can_export(document)
    ]
    if blocked:
        raise HTTPException(
            status_code=409,
            detail={"review_required_invoice_ids": blocked},
        )

    try:
        result = adapter.export_many(documents)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    headers = {
        "Content-Disposition": f'attachment; filename="{result.filename or "winton-import-batch.csv"}"',
        "X-Accounting-Adapter": result.adapter_id,
        "X-Manual-Import-Required": "true" if result.requires_manual_import else "false",
        "X-Exported-Invoice-Count": str(len(documents)),
    }
    if result.warnings:
        headers["X-Adapter-Warning"] = result.warnings[0]
    return Response(content=result.payload, media_type=result.media_type, headers=headers)
