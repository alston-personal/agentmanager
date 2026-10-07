#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any

BRIDGE_SCHEMA = "agentos.session-bridge/v0.1"
SESSION_INDEX_SCHEMA = "agentos.session-index/v0.1"
REQUEST_SCHEMA = "agentos.session-request/v0.1"
RECEIPT_SCHEMA = "agentos.session-receipt/v0.1"
HARVEST_SCHEMA = "agentos.gpt-web-response-harvest/v0.1"
PROVIDER = "gpt-web"
MAX_TEXT = 65536


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def write_descriptor(root: Path, *, ready: bool) -> None:
    atomic_json(root / "bridge.json", {
        "schema": BRIDGE_SCHEMA,
        "provider": PROVIDER,
        "ready": ready,
        "operations": ["discover", "harvest"],
    })


async def discover_page(cdp_url: str):
    from playwright.async_api import async_playwright
    playwright = await async_playwright().start()
    browser = await playwright.chromium.connect_over_cdp(cdp_url)
    candidates = []
    for context in browser.contexts:
        for page in context.pages:
            if page.url.startswith("https://chatgpt.com/"):
                candidates.append(page)
    if not candidates:
        await browser.close()
        await playwright.stop()
        raise RuntimeError("CHATGPT_SESSION_NOT_FOUND")
    page = candidates[-1]
    return playwright, browser, page


async def refresh_sessions(root: Path, cdp_url: str) -> str:
    playwright, browser, page = await discover_page(cdp_url)
    try:
        session_id = "chatgpt-web:" + str(abs(hash(page.url)))
        atomic_json(root / "sessions.json", {
            "schema": SESSION_INDEX_SCHEMA,
            "provider": PROVIDER,
            "sessions": [{
                "session_id": session_id,
                "url": page.url,
                "title": await page.title(),
                "ready": True,
                "capabilities": ["agent.context.harvest"],
            }],
            "observed_at": now(),
        })
        return session_id
    finally:
        await browser.close()
        await playwright.stop()


def _validate_request(payload: dict[str, Any]) -> tuple[str, str]:
    if payload.get("schema") != REQUEST_SCHEMA:
        raise ValueError("invalid session request schema")
    if payload.get("provider") != PROVIDER or payload.get("operation") != "harvest":
        raise ValueError("unsupported provider or operation")
    inner = payload.get("payload")
    if not isinstance(inner, dict) or inner.get("schema") != HARVEST_SCHEMA:
        raise ValueError("invalid GPT Web harvest request")
    if inner.get("selector") != "assistant.response_by_request_id":
        raise ValueError("unsupported GPT Web harvest selector")
    request_id = str(inner.get("request_id") or "").strip()
    if not request_id or len(request_id) > 128:
        raise ValueError("invalid request_id")
    session_id = str(payload.get("session_id") or "").strip()
    if not session_id:
        raise ValueError("session_id is required")
    return session_id, request_id


async def harvest(cdp_url: str, *, session_id: str, request_id: str) -> str:
    playwright, browser, page = await discover_page(cdp_url)
    try:
        # Read only assistant-authored message DOM. Do not inspect user messages,
        # arbitrary page text, credentials, storage, cookies, or network traffic.
        messages = page.locator('[data-message-author-role="assistant"]')
        count = await messages.count()
        for index in range(count - 1, -1, -1):
            text = (await messages.nth(index).inner_text()).strip()
            if request_id in text:
                if len(text) > MAX_TEXT:
                    raise RuntimeError("GPT_WEB_RESPONSE_TOO_LARGE")
                return text
        raise RuntimeError("GPT_WEB_RESPONSE_NOT_READY")
    finally:
        await browser.close()
        await playwright.stop()


async def process_one(root: Path, cdp_url: str, path: Path) -> None:
    request = json.loads(path.read_text(encoding="utf-8-sig"))
    request_id = str(request.get("request_id") or path.stem)
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "request_id": request_id,
        "provider": PROVIDER,
        "session_id": request.get("session_id"),
        "operation": request.get("operation"),
        "completed_at": now(),
        "ok": False,
    }
    try:
        session_id, correlation_id = _validate_request(request)
        text = await harvest(cdp_url, session_id=session_id, request_id=correlation_id)
        receipt["ok"] = True
        receipt["result"] = {
            "request_id": correlation_id,
            "assistant_text": text,
        }
    except Exception as exc:
        receipt["error"] = f"{type(exc).__name__}: {exc}"
    atomic_json(root / "receipts" / f"{request_id}.json", receipt)
    done = root / "processed"
    done.mkdir(parents=True, exist_ok=True)
    os.replace(path, done / path.name)


async def tick(root: Path, cdp_url: str) -> int:
    write_descriptor(root, ready=False)
    try:
        await refresh_sessions(root, cdp_url)
        write_descriptor(root, ready=True)
    except Exception:
        return 2
    request_dir = root / "requests"
    request_dir.mkdir(parents=True, exist_ok=True)
    processed = 0
    for path in sorted(request_dir.glob("*.json")):
        await process_one(root, cdp_url, path)
        processed += 1
    return 0 if processed >= 0 else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bridge-root", type=Path, default=Path(os.environ.get("AGENTOS_GPT_WEB_BRIDGE", "/home/ubuntu/agent-data/runtime/gpt-web-bridge")))
    ap.add_argument("--cdp-url", default=os.environ.get("AGENTOS_GPT_WEB_CDP_URL", "http://127.0.0.1:9222"))
    args = ap.parse_args()
    return asyncio.run(tick(args.bridge_root.expanduser().resolve(), args.cdp_url))


if __name__ == "__main__":
    raise SystemExit(main())
