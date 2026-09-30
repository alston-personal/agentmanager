from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from agentos_node.session_bridge import (
    BRIDGE_SCHEMA,
    RECEIPT_SCHEMA,
    REQUEST_SCHEMA,
    SESSION_INDEX_SCHEMA,
)

EVENT_SCHEMA = "agentos.surface-event/v1"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(path)
    os.chmod(path, 0o600)


def first_visible(page, selectors: Iterable[str], *, timeout_ms: int = 250):
    for selector in selectors:
        try:
            loc = page.locator(selector)
            for i in range(min(loc.count(), 12)):
                item = loc.nth(i)
                try:
                    if item.is_visible(timeout=timeout_ms):
                        return item
                except Exception:
                    pass
        except Exception:
            pass
    return None


def body_text(page, *, limit: int = 16000) -> str:
    try:
        return page.locator("body").inner_text(timeout=1500)[:limit]
    except Exception:
        return ""


def title(page) -> str:
    try:
        return page.title()[:300]
    except Exception:
        return ""


def stable_session_id(prefix: str, url: str, preferred: str | None = None) -> str:
    if preferred:
        return f"{prefix}:{preferred[:96]}"
    return f"{prefix}:url:{hashlib.sha256(url.encode('utf-8')).hexdigest()[:20]}"


@dataclass(frozen=True)
class WebSurfaceAdapter:
    provider: str
    root: Path
    hosts: tuple[str, ...]
    composer_selectors: tuple[str, ...]
    classify: Callable[[Any], dict[str, Any]]
    harvest: Callable[[Any], list[str]]
    cdp_url: str = "http://127.0.0.1:9222"
    novnc_url: str = "http://127.0.0.1:6080/vnc.html"
    max_context_chars: int = 8000

    def event(self, event: str, *, session_id: str | None = None, state: str | None = None, detail: str | None = None) -> None:
        target = self.root / "events.jsonl"
        target.parent.mkdir(parents=True, exist_ok=True)
        payload: dict[str, Any] = {
            "schema": EVENT_SCHEMA,
            "provider": self.provider,
            "session_id": session_id,
            "state": state,
            "event": event,
            "observed_at": utc_now(),
        }
        if detail:
            payload["detail"] = str(detail)[:500]
        with target.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
        os.chmod(target, 0o600)

    def write_descriptor(self, session_state: str = "UNKNOWN") -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        os.chmod(self.root, 0o700)
        atomic_json(self.root / "bridge.json", {
            "schema": BRIDGE_SCHEMA,
            "provider": self.provider,
            "ready": True,
            "session_state": session_state,
            "operations": ["discover", "attach", "snapshot", "inject", "harvest", "handoff"],
            "transport": "playwright-cdp",
            "cdp_url": self.cdp_url,
            "persistent_profile": True,
            "interactive_submit_default": False,
        })

    def with_browser(self):
        from playwright.sync_api import sync_playwright
        p = sync_playwright().start()
        browser = p.chromium.connect_over_cdp(self.cdp_url)
        if not browser.contexts:
            p.stop()
            raise RuntimeError(f"{self.provider}_no_browser_context")
        return p, browser

    def composer(self, page):
        return first_visible(page, self.composer_selectors)

    def matches(self, url: str) -> bool:
        lowered = str(url or "").lower()
        return any(host in lowered for host in self.hosts)

    def snapshot_sessions(self) -> dict[str, Any]:
        p, browser = self.with_browser()
        try:
            sessions = []
            for page in browser.contexts[0].pages:
                row = self.classify(page)
                if self.matches(row.get("url") or "") or row.get("state") == "LOGIN_REQUIRED":
                    sessions.append(row)
            payload = {
                "schema": SESSION_INDEX_SCHEMA,
                "provider": self.provider,
                "observed_at": utc_now(),
                "sessions": sessions,
            }
            atomic_json(self.root / "sessions.json", payload)
            state = "READY" if any(x.get("state") == "READY" for x in sessions) else (
                "LOGIN_REQUIRED" if any(x.get("state") == "LOGIN_REQUIRED" for x in sessions) else "UNKNOWN"
            )
            self.write_descriptor(state)
            if state == "READY":
                row = next(x for x in sessions if x.get("state") == "READY")
                self.event("session_ready", session_id=row.get("session_id"), state="ready")
            elif state == "LOGIN_REQUIRED":
                row = next(x for x in sessions if x.get("state") == "LOGIN_REQUIRED")
                self.event("login_required", session_id=row.get("session_id"), state="login_required")
            return payload
        finally:
            # The Chromium process belongs to the shared GUI Worker.  Only stop
            # this Playwright client; never call browser.close() on a CDP attach.
            p.stop()

    def find_page(self, browser, session_id: str | None):
        candidates = []
        for page in browser.contexts[0].pages:
            row = self.classify(page)
            if not (self.matches(row.get("url") or "") or row.get("state") == "LOGIN_REQUIRED"):
                continue
            candidates.append((page, row))
            if session_id and row.get("session_id") == session_id:
                return page, row
        if session_id:
            raise LookupError(f"{self.provider}_session_not_found")
        ready = next(((p, r) for p, r in candidates if r.get("state") == "READY"), None)
        if ready:
            return ready
        if candidates:
            return candidates[0]
        raise LookupError(f"{self.provider}_no_session")

    def receipt(self, request: dict[str, Any], *, ok: bool, state: str, output: dict[str, Any] | None = None, error: str | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema": RECEIPT_SCHEMA,
            "request_id": request["request_id"],
            "provider": self.provider,
            "operation": request.get("operation"),
            "session_id": request.get("session_id"),
            "ok": ok,
            "state": state,
            "output": dict(output or {}),
            "completed_at": utc_now(),
        }
        if error:
            payload["error"] = str(error)[:800]
        return payload

    def process_request(self, request: dict[str, Any]) -> dict[str, Any]:
        if request.get("schema") != REQUEST_SCHEMA or request.get("provider") != self.provider:
            raise ValueError(f"invalid {self.provider} session request")
        operation = str(request.get("operation") or "")
        if operation == "discover":
            return self.receipt(request, ok=True, state="ready", output=self.snapshot_sessions())

        p, browser = self.with_browser()
        try:
            page, row = self.find_page(browser, request.get("session_id"))
            if row.get("state") != "READY" and operation not in {"snapshot", "handoff"}:
                if row.get("state") == "LOGIN_REQUIRED":
                    self.event("login_required", session_id=row.get("session_id"), state="login_required")
                return self.receipt(request, ok=False, state=str(row.get("state") or "unknown").lower(), output=row, error="session_not_ready")

            if operation == "attach":
                self.event("session_ready", session_id=row.get("session_id"), state="ready")
                return self.receipt(request, ok=True, state="ready", output={"attached": True, **row})

            if operation == "snapshot":
                return self.receipt(request, ok=True, state=str(row.get("state") or "unknown").lower(), output=row)

            if operation == "inject":
                payload = request.get("payload") or {}
                if payload.get("submit") not in (None, False):
                    self.event("needs_human", session_id=row.get("session_id"), state="needs_human", detail="interactive submit is disabled by default")
                    return self.receipt(request, ok=False, state="needs_human", output=row, error="interactive_submit_disabled")
                value = str(payload.get("text") or "")
                if len(value) > self.max_context_chars:
                    return self.receipt(request, ok=False, state="provider_error", output=row, error="context_too_large")
                composer = self.composer(page)
                if composer is None:
                    return self.receipt(request, ok=False, state="provider_error", output=row, error="composer_not_found")
                try:
                    composer.fill(value)
                except Exception:
                    composer.click()
                    page.keyboard.press("ControlOrMeta+A")
                    page.keyboard.type(value)
                return self.receipt(request, ok=True, state="ready", output={**row, "draft_prepared": True, "submitted": False, "draft_length": len(value)})

            if operation == "harvest":
                payload = request.get("payload") or {}
                output: dict[str, Any] = {**row, "content_included": False}
                if payload.get("include_content") is True:
                    output["assistant_messages"] = self.harvest(page)[-5:]
                    output["content_included"] = True
                return self.receipt(request, ok=True, state="ready", output=output)

            if operation == "handoff":
                self.event("needs_human", session_id=row.get("session_id"), state="needs_human")
                return self.receipt(request, ok=True, state="needs_human", output={
                    **row,
                    "human_required": True,
                    "novnc_url": self.novnc_url,
                })

            return self.receipt(request, ok=False, state="provider_error", output=row, error="unsupported_operation")
        finally:
            p.stop()

    def run_once(self) -> int:
        self.write_descriptor()
        try:
            self.snapshot_sessions()
        except Exception as exc:
            self.event("provider_error", state="provider_error", detail=f"{type(exc).__name__}:{exc}")
        requests = self.root / "requests"
        receipts = self.root / "receipts"
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
                receipt = self.process_request(request)
            except Exception as exc:
                request_id = path.stem
                receipt = {
                    "schema": RECEIPT_SCHEMA,
                    "request_id": request_id,
                    "provider": self.provider,
                    "operation": "unknown",
                    "ok": False,
                    "state": "provider_error",
                    "output": {},
                    "error": f"{type(exc).__name__}: {exc}"[:800],
                    "completed_at": utc_now(),
                }
                self.event("provider_error", state="provider_error", detail=receipt["error"])
            atomic_json(target, receipt)
            path.unlink(missing_ok=True)
            processed += 1
        return processed
