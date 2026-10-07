#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import time
import urllib.request
import urllib.parse
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


def _json_get(url: str) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": "agentos-gpt-web-bridge/0.2"})
    with urllib.request.urlopen(req, timeout=5) as response:
        return json.loads(response.read(1024 * 1024))


def _targets(cdp_url: str) -> list[dict[str, Any]]:
    base = cdp_url.rstrip("/")
    payload = _json_get(base + "/json/list")
    if not isinstance(payload, list):
        raise RuntimeError("CDP_TARGET_LIST_INVALID")
    return [item for item in payload if isinstance(item, dict)]


def _create_target(cdp_url: str, url: str) -> dict[str, Any]:
    base = cdp_url.rstrip("/")
    encoded = urllib.parse.quote(url, safe=":/?=&")
    req = urllib.request.Request(
        base + "/json/new?" + encoded,
        method="PUT",
        headers={"User-Agent": "agentos-gpt-web-bridge/0.3"},
    )
    with urllib.request.urlopen(req, timeout=5) as response:
        payload = json.loads(response.read(1024 * 1024))
    if not isinstance(payload, dict) or not payload.get("webSocketDebuggerUrl"):
        raise RuntimeError("CDP_TARGET_CREATE_FAILED")
    return payload


def _chatgpt_target(cdp_url: str, *, create_if_missing: bool = False) -> dict[str, Any]:
    candidates = [
        item for item in _targets(cdp_url)
        if str(item.get("type") or "") == "page"
        and str(item.get("url") or "").startswith("https://chatgpt.com/")
        and str(item.get("webSocketDebuggerUrl") or "")
    ]
    if candidates:
        return candidates[-1]
    if not create_if_missing:
        raise RuntimeError("CHATGPT_SESSION_NOT_FOUND")
    target = _create_target(cdp_url, "https://chatgpt.com/")
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        url = str(target.get("url") or "")
        if url.startswith("https://chatgpt.com/"):
            return target
        time.sleep(0.25)
        matches = [
            item for item in _targets(cdp_url)
            if str(item.get("id") or "") == str(target.get("id") or "")
        ]
        if matches:
            target = matches[0]
    return target


class CdpPage:
    def __init__(self, ws_url: str):
        import websocket
        try:
            self.ws = websocket.create_connection(ws_url, timeout=5, suppress_origin=True)
        except websocket.WebSocketTimeoutException as exc:
            raise TimeoutError("CDP_WS_CONNECT_TIMEOUT") from exc
        except Exception as exc:
            raise RuntimeError(f"CDP_WS_CONNECT_FAILED:{type(exc).__name__}:{exc}") from exc
        self.ws.settimeout(5)
        self.seq = 0

    def close(self) -> None:
        try:
            self.ws.close()
        except Exception:
            pass

    def call(self, method: str, params: dict[str, Any] | None = None, *, session_id: str | None = None) -> dict[str, Any]:
        self.seq += 1
        call_id = self.seq
        message: dict[str, Any] = {"id": call_id, "method": method, "params": params or {}}
        if session_id:
            message["sessionId"] = session_id
        self.ws.send(json.dumps(message))
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            try:
                raw = self.ws.recv()
            except Exception as exc:
                if type(exc).__name__ == "WebSocketTimeoutException":
                    raise TimeoutError(f"CDP_COMMAND_RECV_TIMEOUT:{method}") from exc
                raise RuntimeError(f"CDP_COMMAND_RECV_FAILED:{method}:{type(exc).__name__}:{exc}") from exc
            message = json.loads(raw)
            if message.get("id") != call_id:
                continue
            if "error" in message:
                raise RuntimeError("CDP_" + method.replace(".", "_") + "_FAILED:" + str(message["error"]))
            result = message.get("result")
            return result if isinstance(result, dict) else {}
        raise TimeoutError("CDP_COMMAND_TIMEOUT:" + method)

    def evaluate(self, expression: str, *, session_id: str | None = None) -> Any:
        result = self.call("Runtime.evaluate", {
            "expression": expression,
            "returnByValue": True,
            "awaitPromise": True,
        }, session_id=session_id)
        obj = result.get("result") or {}
        if obj.get("subtype") == "error":
            raise RuntimeError("CDP_EVALUATE_ERROR")
        return obj.get("value")


class CdpTargetSession:
    def __init__(self, connection: CdpPage, *, session_id: str | None, mode: str):
        self.connection = connection
        self.session_id = session_id
        self.mode = mode

    def close(self) -> None:
        self.connection.close()

    def call(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.connection.call(method, params, session_id=self.session_id)

    def evaluate(self, expression: str) -> Any:
        return self.connection.evaluate(expression, session_id=self.session_id)


def _browser_ws_url(cdp_url: str) -> str:
    payload = _json_get(cdp_url.rstrip("/") + "/json/version")
    ws = str((payload or {}).get("webSocketDebuggerUrl") or "")
    if not ws:
        raise RuntimeError("CDP_BROWSER_WS_MISSING")
    return ws


def _open_target_connection(cdp_url: str, target: dict[str, Any]) -> CdpTargetSession:
    target_id = str(target.get("id") or "")
    direct_error: str | None = None
    direct = None
    try:
        direct = CdpPage(str(target.get("webSocketDebuggerUrl") or ""))
        endpoint = CdpTargetSession(direct, session_id=None, mode="page-ws")
        href = endpoint.evaluate("location.href")
        if isinstance(href, str) and href.startswith("https://chatgpt.com/"):
            return endpoint
        direct_error = f"unexpected_href:{href!r}"
    except Exception as exc:
        direct_error = f"{type(exc).__name__}:{exc}"
    finally:
        if direct is not None and direct_error is not None:
            direct.close()

    browser = None
    try:
        browser = CdpPage(_browser_ws_url(cdp_url))
        browser.call("Browser.getVersion")
        attached = browser.call("Target.attachToTarget", {
            "targetId": target_id,
            "flatten": True,
        })
        sid = str(attached.get("sessionId") or "")
        if not sid:
            raise RuntimeError("CDP_ATTACH_SESSION_ID_MISSING")
        endpoint = CdpTargetSession(browser, session_id=sid, mode="browser-session")
        href = endpoint.evaluate("location.href")
        if not isinstance(href, str) or not href.startswith("https://chatgpt.com/"):
            endpoint.close()
            raise RuntimeError(f"CDP_ATTACHED_UNEXPECTED_HREF:{href!r}")
        return endpoint
    except Exception as exc:
        if browser is not None:
            browser.close()
        raise RuntimeError(
            "CDP_TARGET_OPEN_FAILED:"
            + f"direct={direct_error};browser_session={type(exc).__name__}:{exc}"
        ) from exc


def _responsive_chatgpt_target(cdp_url: str) -> tuple[dict[str, Any], str, str]:
    target = _chatgpt_target(cdp_url, create_if_missing=True)
    candidates = [target] + [
        item for item in reversed(_targets(cdp_url))
        if str(item.get("id") or "") != str(target.get("id") or "")
        and str(item.get("type") or "") == "page"
        and str(item.get("url") or "").startswith("https://chatgpt.com/")
        and str(item.get("webSocketDebuggerUrl") or "")
    ]
    errors: list[str] = []

    def try_target(item: dict[str, Any]) -> tuple[dict[str, Any], str, str] | None:
        endpoint = None
        try:
            endpoint = _open_target_connection(cdp_url, item)
            href = endpoint.evaluate("location.href")
            return item, str(href), endpoint.mode
        except Exception as exc:
            errors.append(f"{item.get('id')}:{type(exc).__name__}:{exc}")
            return None
        finally:
            if endpoint is not None:
                endpoint.close()

    for item in candidates:
        result = try_target(item)
        if result is not None:
            return result

    # A persistent browser can retain a dead renderer indefinitely. Do not keep
    # retrying the same stale ChatGPT tab: create one fresh page in the same
    # browser profile so authentication cookies/session are preserved.
    fresh = _create_target(cdp_url, "https://chatgpt.com/")
    fresh_id = str(fresh.get("id") or "")
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        matches = [
            item for item in _targets(cdp_url)
            if str(item.get("id") or "") == fresh_id
        ]
        item = matches[0] if matches else fresh
        result = try_target(item)
        if result is not None:
            return result
        time.sleep(0.5)

    raise RuntimeError("CHATGPT_CDP_TARGET_UNRESPONSIVE:" + " | ".join(errors[-8:]))


def refresh_sessions(root: Path, cdp_url: str) -> str:
    target, href, transport = _responsive_chatgpt_target(cdp_url)
    session_id = "chatgpt-web:" + str(target.get("id") or "page")
    atomic_json(root / "sessions.json", {
        "schema": SESSION_INDEX_SCHEMA,
        "provider": PROVIDER,
        "sessions": [{
            "session_id": session_id,
            "url": href,
            "title": target.get("title"),
            "ready": True,
            "capabilities": ["agent.session.invoke", "agent.context.harvest"],
            "transport": transport,
        }],
        "observed_at": now(),
    })
    return session_id


def _page(cdp_url: str) -> CdpTargetSession:
    target = _chatgpt_target(cdp_url)
    return _open_target_connection(cdp_url, target)


def _assistant_text(page: CdpPage, request_id: str) -> str | None:
    expr = """(() => {
      const id = %s;
      const nodes = Array.from(document.querySelectorAll('[data-message-author-role="assistant"]'));
      for (let i = nodes.length - 1; i >= 0; i--) {
        const text = (nodes[i].innerText || nodes[i].textContent || '').trim();
        if (text.includes(id)) return text;
      }
      return null;
    })()""" % json.dumps(request_id)
    value = page.evaluate(expr)
    return str(value) if isinstance(value, str) else None


def invoke(cdp_url: str, *, session_id: str, request_id: str, inner: dict[str, Any]) -> str:
    image = Path(str(inner["image_path"])).expanduser().resolve()
    allowed_raw = os.environ.get("AGENTOS_GPT_WEB_ALLOWED_ROOTS", "/home/ubuntu/agentmanager/benchmarks/invoice_handwriting/fixtures")
    allowed = [Path(x).expanduser().resolve() for x in allowed_raw.split(os.pathsep) if x.strip()]
    if not any(_inside(image, root) for root in allowed):
        raise PermissionError("GPT Web invoke image_path outside allowed roots")
    if not image.is_file() or image.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise ValueError("GPT Web invoke requires an allowed image file")
    if image.stat().st_size > 12 * 1024 * 1024:
        raise ValueError("GPT Web invoke image too large")

    page = _page(cdp_url)
    try:
        element = page.call("Runtime.evaluate", {
            "expression": "document.querySelector('input[type=file]')",
            "returnByValue": False,
        }).get("result") or {}
        object_id = element.get("objectId")
        if not object_id:
            raise RuntimeError("GPT_WEB_FILE_INPUT_NOT_FOUND")
        page.call("DOM.setFileInputFiles", {"objectId": object_id, "files": [str(image)]})

        prompt = str(inner["prompt"])
        found = page.evaluate("""(() => {
          const el = document.querySelector('#prompt-textarea') ||
                     Array.from(document.querySelectorAll('[contenteditable="true"]')).pop();
          if (!el) return false;
          el.focus();
          return true;
        })()""")
        if found is not True:
            raise RuntimeError("GPT_WEB_COMPOSER_NOT_FOUND")
        page.call("Input.insertText", {"text": prompt})
        page.call("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13})
        page.call("Input.dispatchKeyEvent", {"type": "keyUp", "key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13})

        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            text = _assistant_text(page, request_id)
            if text:
                if len(text) > MAX_TEXT:
                    raise RuntimeError("GPT_WEB_RESPONSE_TOO_LARGE")
                return text
            time.sleep(0.5)
        raise RuntimeError("GPT_WEB_RESPONSE_TIMEOUT")
    finally:
        page.close()


def harvest(cdp_url: str, *, session_id: str, request_id: str) -> str:
    page = _page(cdp_url)
    try:
        text = _assistant_text(page, request_id)
        if not text:
            raise RuntimeError("GPT_WEB_RESPONSE_NOT_READY")
        if len(text) > MAX_TEXT:
            raise RuntimeError("GPT_WEB_RESPONSE_TOO_LARGE")
        return text
    finally:
        page.close()


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


def process_one(root: Path, cdp_url: str, path: Path) -> None:
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
            text = invoke(cdp_url, session_id=session_id, request_id=correlation_id, inner=inner)
        else:
            text = harvest(cdp_url, session_id=session_id, request_id=correlation_id)
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


def tick(root: Path, cdp_url: str) -> int:
    write_descriptor(root, ready=False)
    try:
        refresh_sessions(root, cdp_url)
        write_descriptor(root, ready=True)
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        atomic_json(root / "bridge.json", {
            "schema": BRIDGE_SCHEMA,
            "provider": PROVIDER,
            "ready": False,
            "operations": ["discover", "invoke", "harvest"],
            "error": error,
            "observed_at": now(),
        })
        print("gpt_web_bridge_error=" + error, flush=True)
        return 2
    request_dir = root / "requests"
    request_dir.mkdir(parents=True, exist_ok=True)
    processed = 0
    for path in sorted(request_dir.glob("*.json")):
        process_one(root, cdp_url, path)
        processed += 1
    return 0 if processed >= 0 else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bridge-root", type=Path, default=Path(os.environ.get("AGENTOS_GPT_WEB_BRIDGE", "/home/ubuntu/agent-data/runtime/gpt-web-bridge")))
    ap.add_argument("--cdp-url", default=os.environ.get("AGENTOS_GPT_WEB_CDP_URL", "http://127.0.0.1:9222"))
    args = ap.parse_args()
    return tick(args.bridge_root.expanduser().resolve(), args.cdp_url)


if __name__ == "__main__":
    raise SystemExit(main())
