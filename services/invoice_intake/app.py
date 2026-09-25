from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, Request, UploadFile
from pydantic import BaseModel

from invoice_core import InvoiceStore

VERSION = "0.3.0"
DATA_ROOT = Path(os.environ.get("INVOICE_DATA_ROOT", "/home/ubuntu/agent-data/invoice-intake"))
MAX_UPLOAD = 12 * 1024 * 1024
DASHBOARD_SESSION = os.environ.get("DASHBOARD_SESSION_URL", "http://127.0.0.1:3000/dashboard/api/auth/session")

store = InvoiceStore(DATA_ROOT)
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
        "ocr_engine": "tesseract-layout-v2-async",
        "authenticated": bool(session.get("loggedIn")),
        "role": session.get("role") if session.get("loggedIn") else None,
        "continuous_scan": True,
        "immutable_originals": True,
        "database": "sqlite",
    }


@app.post("/v1/ingest")
async def ingest(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
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
        payload = store.ingest(data, file.filename or "camera.jpg", mime)
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
