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
INVOKE_SCHEMA = "agentos.gpt-web-vision-invoke/v0.1"
PROVIDER = "gpt-web"
MAX_TEXT = 65536


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


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
        "operations": ["discover", "invoke", "harvest"],
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
                "capabilities": ["agent.session.invoke", "agent.context.harvest"],
            }],
            "observed_at": now(),
        })
        return session_id
    finally:
        await browser.close()
        await playwright.stop()


def _validate_request(payload: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
    if payload.get("schema") != REQUEST_SCHEMA:
        raise ValueError("invalid session request schema")
    if payload.get("provider") != PROVIDER:
        raise ValueError("unsupported provider")
    operation = str(payload.get("operation") or "")
    if operation not in {"harvest", "invoke"}:
        raise ValueError("unsupported operation")
    inner = payload.get("payload")
    if not isinstance(inner, dict):
        raise ValueError("request payload missing")
    session_id = str(payload.get("session_id") or "").strip()
    if not session_id:
        raise ValueError("session_id is required")
    request_id = str(inner.get("request_id") or "").strip()
    if not request_id or len(request_id) > 128:
        raise ValueError("invalid request_id")

    if operation == "harvest":
        if inner.get("schema") != HARVEST_SCHEMA:
            raise ValueError("invalid GPT Web harvest request")
        if inner.get("selector") != "assistant.response_by_request_id":
            raise ValueError("unsupported GPT Web harvest selector")
    else:
        if inner.get("schema") != INVOKE_SCHEMA:
            raise ValueError("invalid GPT Web invoke request")
        if inner.get("capability") not in {"vision.document.extract", "vision.invoice.extract"}:
            raise ValueError("unsupported GPT Web capability")
        image_path = str(inner.get("image_path") or "").strip()
        prompt = str(inner.get("prompt") or "")
        if not image_path or not prompt or len(prompt) > 12000:
            raise ValueError("invoke requires bounded image_path and prompt")
    return session_id, request_id, inner


async def invoke(cdp_url: str, *, session_id: str, request_id: str, inner: dict[str, Any]) -> str:
    playwright, browser, page = await discover_page(cdp_url)
    try:
        image = Path(str(inner["image_path"])).expanduser().resolve()
        allowed_raw = os.environ.get("AGENTOS_GPT_WEB_ALLOWED_ROOTS", "/home/ubuntu/agentmanager/benchmarks/invoice_handwriting/fixtures")
        allowed = [Path(x).expanduser().resolve() for x in allowed_raw.split(os.pathsep) if x.strip()]
        if not any(_inside(image, root) for root in allowed):
            raise PermissionError("GPT Web invoke image_path outside allowed roots")
        if not image.is_file() or image.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
            raise ValueError("GPT Web invoke requires an allowed image file")
        if image.stat().st_size > 12 * 1024 * 1024:
            raise ValueError("GPT Web invoke image too large")

        file_input = page.locator('input[type="file"]').last
        if await file_input.count() == 0:
            raise RuntimeError("GPT_WEB_FILE_INPUT_NOT_FOUND")
        await file_input.set_input_files(str(image))

        prompt = str(inner["prompt"])
        composer = page.locator('#prompt-textarea')
        if await composer.count() == 0:
            composer = page.locator('[contenteditable="true"]').last
        if await composer.count() == 0:
            raise RuntimeError("GPT_WEB_COMPOSER_NOT_FOUND")
        await composer.fill(prompt)
        await composer.press("Enter")

        deadline = asyncio.get_running_loop().time() + 45
        while asyncio.get_running_loop().time() < deadline:
            messages = page.locator('[data-message-author-role="assistant"]')
            count = await messages.count()
            for index in range(count - 1, -1, -1):
                text = (await messages.nth(index).inner_text()).strip()
                if request_id in text:
                    if len(text) > MAX_TEXT:
                        raise RuntimeError("GPT_WEB_RESPONSE_TOO_LARGE")
                    return text
            await page.wait_for_timeout(500)
        raise RuntimeError("GPT_WEB_RESPONSE_TIMEOUT")
    finally:
        await browser.close()
        await playwright.stop()


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
        session_id, correlation_id, inner = _validate_request(request)
        if request.get("operation") == "invoke":
            text = await invoke(cdp_url, session_id=session_id, request_id=correlation_id, inner=inner)
        else:
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
