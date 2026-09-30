from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agentos_node.session_bridge import (
    BRIDGE_SCHEMA,
    REQUEST_SCHEMA,
    RECEIPT_SCHEMA,
    SESSION_INDEX_SCHEMA,
)

PROVIDER = "chatgpt-web"
EVENT_SCHEMA = "agentos.surface-event/v1"
DEFAULT_ROOT = Path.home() / ".local/share/agentos/chatgpt-web/bridge"
PROBE_STATE = Path.home() / ".local/share/agentos/chatgpt-web/probe-current.json"
CDP_URL = os.environ.get("AGENTOS_GUI_CDP_URL") or "http://127.0.0.1:9222"


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def root() -> Path:
    return Path(os.environ.get("AGENTOS_CHATGPT_WEB_BRIDGE") or DEFAULT_ROOT).expanduser()


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(path)
    os.chmod(path, 0o600)


def _event(event: str, *, session_id: str | None = None, state: str | None = None, detail: str | None = None) -> None:
    target = root() / "events.jsonl"
    target.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "schema": EVENT_SCHEMA,
        "provider": PROVIDER,
        "session_id": session_id,
        "state": state,
        "event": event,
        "observed_at": _now(),
    }
    if detail:
        payload["detail"] = detail[:500]
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
    os.chmod(target, 0o600)


def _probe_state() -> str:
    try:
        payload = json.loads(PROBE_STATE.read_text(encoding="utf-8"))
        return str(payload.get("state") or "UNKNOWN")
    except Exception:
        return "UNKNOWN"


def _write_descriptor() -> None:
    r = root()
    r.mkdir(parents=True, exist_ok=True)
    os.chmod(r, 0o700)
    _atomic_json(r / "bridge.json", {
        "schema": BRIDGE_SCHEMA,
        "provider": PROVIDER,
        "ready": True,
        "session_state": _probe_state(),
        "operations": ["discover", "attach", "snapshot", "inject", "harvest", "handoff"],
        "transport": "playwright-cdp",
        "cdp_url": CDP_URL,
        "persistent_profile": True,
        "interactive_submit_default": False,
    })


def _session_id(url: str) -> str:
    parts = [p for p in url.split("/") if p]
    if "c" in parts:
        i = parts.index("c")
        if i + 1 < len(parts):
            return "chatgpt:" + parts[i + 1][:96]
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:20]
    return "chatgpt:url:" + digest


def _composer(page):
    selectors = [
        "#prompt-textarea",
        '[data-testid="composer-input"]',
        'textarea',
        '[contenteditable="true"]',
    ]
    for selector in selectors:
        loc = page.locator(selector)
        for i in range(min(loc.count(), 10)):
            item = loc.nth(i)
            try:
                if item.is_visible(timeout=250):
                    return item
            except Exception:
                pass
    return None


def _classify(page) -> dict[str, Any]:
    url = str(page.url or "")
    host = ""
    try:
        from urllib.parse import urlparse
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        pass
    composer = _composer(page)
    state = "UNKNOWN"
    if host.endswith("chatgpt.com") and composer is not None:
        state = "READY"
    elif host.endswith("chatgpt.com"):
        body = ""
        try:
            body = page.locator("body").inner_text(timeout=1200)[:12000].lower()
        except Exception:
            pass
        state = "LOGIN_REQUIRED" if ("log in" in body or "sign up" in body or "登入" in body or "註冊" in body) else "CHATGPT_REACHED_NO_COMPOSER"
    else:
        state = "UNEXPECTED_DESTINATION"
    title = ""
    try:
        title = page.title()[:300]
    except Exception:
        pass
    return {
        "session_id": _session_id(url),
        "url": url,
        "title": title,
        "state": state,
        "composer_visible": composer is not None,
    }


def _with_browser():
    from playwright.sync_api import sync_playwright
    p = sync_playwright().start()
    browser = p.chromium.connect_over_cdp(CDP_URL)
    if not browser.contexts:
        p.stop()
        raise RuntimeError("chatgpt_web_no_browser_context")
    return p, browser


def snapshot_sessions() -> dict[str, Any]:
    p, browser = _with_browser()
    try:
        context = browser.contexts[0]
        sessions = []
        for page in context.pages:
            row = _classify(page)
            if "chatgpt.com" in row["url"]:
                sessions.append(row)
        payload = {
            "schema": SESSION_INDEX_SCHEMA,
            "provider": PROVIDER,
            "observed_at": _now(),
            "sessions": sessions,
        }
        _atomic_json(root() / "sessions.json", payload)
        if any(x["state"] == "READY" for x in sessions):
            _event("session_ready", session_id=next(x["session_id"] for x in sessions if x["state"] == "READY"), state="ready")
        elif any(x["state"] == "LOGIN_REQUIRED" for x in sessions):
            _event("login_required", session_id=next(x["session_id"] for x in sessions if x["state"] == "LOGIN_REQUIRED"), state="login_required")
        return payload
    finally:
        p.stop()


def _find_page(browser, session_id: str | None):
    context = browser.contexts[0]
    candidates = []
    for page in context.pages:
        row = _classify(page)
        if "chatgpt.com" not in row["url"]:
            continue
        candidates.append((page, row))
        if session_id and row["session_id"] == session_id:
            return page, row
    if session_id:
        raise LookupError("chatgpt_web_session_not_found")
    ready = next(((p, r) for p, r in candidates if r["state"] == "READY"), None)
    if ready:
        return ready
    if candidates:
        return candidates[0]
    raise LookupError("chatgpt_web_no_session")


def _receipt(request: dict[str, Any], *, ok: bool, state: str, output: dict[str, Any] | None = None, error: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema": RECEIPT_SCHEMA,
        "request_id": request["request_id"],
        "provider": PROVIDER,
        "operation": request.get("operation"),
        "session_id": request.get("session_id"),
        "ok": ok,
        "state": state,
        "output": dict(output or {}),
        "completed_at": _now(),
    }
    if error:
        payload["error"] = error[:800]
    return payload


def process_request(request: dict[str, Any]) -> dict[str, Any]:
    if request.get("schema") != REQUEST_SCHEMA or request.get("provider") != PROVIDER:
        raise ValueError("invalid chatgpt-web session request")
    operation = str(request.get("operation") or "")
    if operation == "discover":
        return _receipt(request, ok=True, state="ready", output=snapshot_sessions())

    p, browser = _with_browser()
    try:
        page, row = _find_page(browser, request.get("session_id"))
        if row["state"] != "READY" and operation not in {"snapshot", "handoff"}:
            if row["state"] == "LOGIN_REQUIRED":
                _event("login_required", session_id=row["session_id"], state="login_required")
            return _receipt(request, ok=False, state=row["state"].lower(), output=row, error="session_not_ready")

        if operation == "attach":
            _event("session_ready", session_id=row["session_id"], state="ready")
            return _receipt(request, ok=True, state="ready", output={"attached": True, **row})

        if operation == "snapshot":
            return _receipt(request, ok=True, state=row["state"].lower(), output=row)

        if operation == "inject":
            payload = request.get("payload") or {}
            if payload.get("submit") not in (None, False):
                _event("needs_human", session_id=row["session_id"], state="needs_human", detail="interactive submit is disabled by default")
                return _receipt(request, ok=False, state="needs_human", output=row, error="interactive_submit_disabled")
            text = str(payload.get("text") or "")
            if len(text) > 8000:
                return _receipt(request, ok=False, state="provider_error", output=row, error="context_too_large")
            composer = _composer(page)
            if composer is None:
                return _receipt(request, ok=False, state="provider_error", output=row, error="composer_not_found")
            composer.fill(text)
            return _receipt(request, ok=True, state="ready", output={**row, "draft_prepared": True, "submitted": False, "draft_length": len(text)})

        if operation == "harvest":
            payload = request.get("payload") or {}
            output: dict[str, Any] = {**row, "content_included": False}
            if payload.get("include_content") is True:
                messages = page.locator('[data-message-author-role="assistant"]')
                extracted = []
                for i in range(max(0, messages.count() - 5), messages.count()):
                    try:
                        extracted.append(messages.nth(i).inner_text(timeout=1000)[:6000])
                    except Exception:
                        pass
                output["assistant_messages"] = extracted
                output["content_included"] = True
            return _receipt(request, ok=True, state="ready", output=output)

        if operation == "handoff":
            _event("needs_human", session_id=row["session_id"], state="needs_human")
            return _receipt(request, ok=True, state="needs_human", output={
                **row,
                "human_required": True,
                "novnc_url": "http://127.0.0.1:6080/vnc.html",
            })

        return _receipt(request, ok=False, state="provider_error", output=row, error="unsupported_operation")
    finally:
        p.stop()


def run_once() -> int:
    _write_descriptor()
    try:
        snapshot_sessions()
    except Exception as exc:
        _event("provider_error", state="provider_error", detail=f"{type(exc).__name__}:{exc}")
    requests = root() / "requests"
    receipts = root() / "receipts"
    requests.mkdir(parents=True, exist_ok=True)
    receipts.mkdir(parents=True, exist_ok=True)
    os.chmod(requests, 0o700)
    os.chmod(receipts, 0o700)
    processed = 0
    for path in sorted(requests.glob("session-*.json")):
        target = receipts / path.name
        if target.exists():
            path.unlink(missing_ok=True)
            continue
        try:
            request = json.loads(path.read_text(encoding="utf-8"))
            receipt = process_request(request)
        except Exception as exc:
            request_id = path.stem
            receipt = {
                "schema": RECEIPT_SCHEMA,
                "request_id": request_id,
                "provider": PROVIDER,
                "operation": "unknown",
                "ok": False,
                "state": "provider_error",
                "output": {},
                "error": f"{type(exc).__name__}: {exc}"[:800],
                "completed_at": _now(),
            }
            _event("provider_error", state="provider_error", detail=receipt["error"])
        _atomic_json(target, receipt)
        path.unlink(missing_ok=True)
        processed += 1
    return processed


def serve(interval: float = 0.5) -> None:
    _write_descriptor()
    while True:
        run_once()
        time.sleep(interval)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    if args.serve:
        serve()
        return 0
    run_once()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
