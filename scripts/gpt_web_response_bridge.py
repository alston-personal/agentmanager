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
    # /uc/ is known to expose no role-bearing messages in the invoice
    # acceptance. Do not reuse that surface for another invoke.
    candidates = [
        item for item in _targets(cdp_url)
        if item.get("type") == "page"
        and str(item.get("url") or "").startswith("https://chatgpt.com/")
        and not str(item.get("url") or "").startswith("https://chatgpt.com/uc/")
        and item.get("webSocketDebuggerUrl")
    ]
    if candidates:
        target = candidates[-1]
    else:
        # Stay in the existing Chromium profile; never create credentials or
        # switch another account's profile. A fresh target may still redirect
        # to /uc/ and must then fail closed before upload.
        target = _create_target(cdp_url, "https://chatgpt.com/")
    page = _open_target_connection(cdp_url, target)
    try:
        href = page.evaluate("location.href")
        if str(href).startswith("https://chatgpt.com/uc/"):
            raise RuntimeError("GPT_WEB_UNSUPPORTED_CONVERSATION_ROUTE:/uc/")
        return page
    except Exception:
        page.close()
        raise


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



COMPOSER_SELECTORS = [
    "#prompt-textarea",
    '[data-testid="composer-text-input"]',
    'textarea',
    '[role="textbox"]',
    '.ProseMirror[contenteditable="true"]',
    '[contenteditable="true"]',
]


def _composer_snapshot(page: Any) -> dict[str, Any]:
    selectors_json = json.dumps(COMPOSER_SELECTORS)
    expr = """(() => {
      const selectors = %s;
      const result = {
        href: location.href,
        title: document.title,
        readyState: document.readyState,
        fileInputs: document.querySelectorAll('input[type="file"]').length,
        loginRequired: false,
        candidates: []
      };
      const authTexts = Array.from(document.querySelectorAll('a,button'))
        .map(x => (x.innerText || x.textContent || '').trim().toLowerCase())
        .filter(Boolean);
      result.loginRequired = authTexts.some(t =>
        t === 'log in' || t === 'sign up' || t === '登入' || t === '註冊'
      );
      for (const selector of selectors) {
        const nodes = Array.from(document.querySelectorAll(selector));
        let visible = 0;
        for (const node of nodes) {
          const r = node.getBoundingClientRect();
          if (r.width > 0 && r.height > 0) visible++;
        }
        result.candidates.push({selector, count:nodes.length, visible});
      }
      return result;
    })()""" % selectors_json
    value = page.evaluate(expr)
    return value if isinstance(value, dict) else {"invalid_snapshot": True}


def _focus_composer(page: Any, *, timeout_seconds: float = 12.0) -> dict[str, Any]:
    selectors_json = json.dumps(COMPOSER_SELECTORS)
    deadline = time.monotonic() + timeout_seconds
    last_snapshot: dict[str, Any] = {}
    while time.monotonic() < deadline:
        expr = """(() => {
          const selectors = %s;
          for (const selector of selectors) {
            const nodes = Array.from(document.querySelectorAll(selector));
            for (let i = nodes.length - 1; i >= 0; i--) {
              const el = nodes[i];
              const r = el.getBoundingClientRect();
              const disabled = el.disabled === true || el.getAttribute('aria-disabled') === 'true';
              if (r.width > 0 && r.height > 0 && !disabled) {
                el.focus();
                return {
                  ok: true,
                  selector,
                  tag: el.tagName,
                  contenteditable: el.getAttribute('contenteditable'),
                  role: el.getAttribute('role'),
                  testid: el.getAttribute('data-testid')
                };
              }
            }
          }
          return {ok:false};
        })()""" % selectors_json
        value = page.evaluate(expr)
        if isinstance(value, dict) and value.get("ok") is True:
            return value
        last_snapshot = _composer_snapshot(page)
        if last_snapshot.get("loginRequired") is True:
            raise RuntimeError("GPT_WEB_LOGIN_REQUIRED")
        time.sleep(0.4)
    raise RuntimeError(
        "GPT_WEB_COMPOSER_NOT_FOUND:" + json.dumps(last_snapshot, ensure_ascii=False, sort_keys=True)
    )



SEND_SELECTORS = [
    '[data-testid="send-button"]',
    'button[aria-label="Send prompt"]',
    'button[aria-label*="Send"]',
    'button[aria-label*="傳送"]',
    'button[aria-label*="送出"]',
    'form button[type="submit"]',
]


def _submission_snapshot(page: Any, request_id: str) -> dict[str, Any]:
    composer_json = json.dumps(COMPOSER_SELECTORS)
    send_json = json.dumps(SEND_SELECTORS)
    expr = """(() => {
      const composerSelectors = %s;
      const sendSelectors = %s;
      let composerText = '';
      for (const selector of composerSelectors) {
        const nodes = Array.from(document.querySelectorAll(selector));
        for (let i = nodes.length - 1; i >= 0; i--) {
          const el = nodes[i];
          const r = el.getBoundingClientRect();
          if (r.width > 0 && r.height > 0) {
            composerText = (el.value || el.innerText || el.textContent || '');
            break;
          }
        }
        if (composerText) break;
      }
      const send = [];
      for (const selector of sendSelectors) {
        const nodes = Array.from(document.querySelectorAll(selector));
        let visible=0, enabled=0;
        for (const node of nodes) {
          const r=node.getBoundingClientRect();
          const disabled=node.disabled === true || node.getAttribute('aria-disabled') === 'true';
          if (r.width > 0 && r.height > 0) {
            visible++;
            if (!disabled) enabled++;
          }
        }
        send.push({selector,count:nodes.length,visible,enabled});
      }
      const users = Array.from(document.querySelectorAll('[data-message-author-role="user"]'));
      const correlatedUsers = users.filter(node => (node.innerText || node.textContent || '').includes(%s));
      const assistants = Array.from(document.querySelectorAll('[data-message-author-role="assistant"]'));
      const lastAssistant = assistants.length ? (assistants[assistants.length - 1].innerText || assistants[assistants.length - 1].textContent || '') : '';
      const stopSelectors = [
        '[data-testid="stop-button"]',
        'button[aria-label*="Stop"]',
        'button[aria-label*="停止"]'
      ];
      let generating=false;
      for (const selector of stopSelectors) {
        for (const node of document.querySelectorAll(selector)) {
          const r=node.getBoundingClientRect();
          if (r.width > 0 && r.height > 0) generating=true;
        }
      }
      // Structural-only evidence: never export message text, prompt, or image data.
      const frameSummary = Array.from(document.querySelectorAll('iframe')).slice(0, 12).map(el => ({
        visible: el.getBoundingClientRect().width > 0 && el.getBoundingClientRect().height > 0,
        sameOrigin: (() => { try { return !!el.contentDocument; } catch (_) { return false; } })()
      }));
      const attachmentSummary = {
        fileInputs: document.querySelectorAll('input[type="file"]').length,
        fileInputStates: Array.from(document.querySelectorAll('input[type="file"]')).slice(0, 8).map(el => ({
          acceptsImage: (el.accept || '').toLowerCase().includes('image'),
          acceptsAny: !(el.accept || '').trim(),
          selectedCount: (el.files || []).length,
          connected: el.isConnected
        })),
        imagePreviewCount: document.querySelectorAll('[data-testid*="attachment"], [data-testid*="upload"], [data-testid*="preview"]').length,
        imageElements: document.querySelectorAll('img').length,
        pendingIndicators: document.querySelectorAll('[aria-busy="true"], [role="progressbar"]').length
      };
      const messageNodes = Array.from(document.querySelectorAll('[data-message-author-role]'));
      const roleCounts = {};
      for (const node of messageNodes) {
        const role = node.getAttribute('data-message-author-role') || 'unknown';
        roleCounts[role] = (roleCounts[role] || 0) + 1;
      }
      return {
        pagePath: location.pathname.slice(0, 160),
        readyState: document.readyState,
        roleCounts,
        frameSummary,
        attachmentSummary,
        messageNodes: messageNodes.length,
        composerHasRequest: composerText.includes(%s),
        composerChars: composerText.length,
        send,
        userCount: users.length,
        correlatedUserCount: correlatedUsers.length,
        assistantCount: assistants.length,
        lastAssistantChars: lastAssistant.length,
        lastAssistantHasRequest: lastAssistant.includes(%s),
        generating
      };
    })()""" % (composer_json, send_json, json.dumps(request_id), json.dumps(request_id), json.dumps(request_id))
    value=page.evaluate(expr)
    return value if isinstance(value, dict) else {"invalid_snapshot":True}


def _click_send(page: Any, *, request_id: str, timeout_seconds: float = 12.0) -> dict[str, Any]:
    selectors_json=json.dumps(SEND_SELECTORS)
    deadline=time.monotonic()+timeout_seconds
    last: dict[str, Any]={}
    while time.monotonic() < deadline:
        expr="""(() => {
          const selectors=%s;
          for (const selector of selectors) {
            const nodes=Array.from(document.querySelectorAll(selector));
            for (let i=nodes.length-1; i>=0; i--) {
              const el=nodes[i];
              const r=el.getBoundingClientRect();
              const disabled=el.disabled === true || el.getAttribute('aria-disabled') === 'true';
              if (r.width > 0 && r.height > 0 && !disabled) {
                el.click();
                return {ok:true,selector};
              }
            }
          }
          return {ok:false};
        })()""" % selectors_json
        value=page.evaluate(expr)
        if isinstance(value, dict) and value.get("ok") is True:
            return value
        last=_submission_snapshot(page,request_id)
        time.sleep(0.4)
    raise RuntimeError(
        "GPT_WEB_SEND_CONTROL_NOT_READY:" + json.dumps(last,ensure_ascii=False,sort_keys=True)
    )


def _confirm_submit(page: Any, *, request_id: str, baseline_assistants: int, baseline_users: int = 0, timeout_seconds: float = 8.0) -> dict[str, Any]:
    deadline=time.monotonic()+timeout_seconds
    last: dict[str, Any]={}
    while time.monotonic() < deadline:
        last=_submission_snapshot(page,request_id)
        if (
            int(last.get("assistantCount") or 0) > baseline_assistants
            or last.get("generating") is True
            or (int(last.get("userCount") or 0) > baseline_users and int(last.get("correlatedUserCount") or 0) > 0)
        ):
            return last
        time.sleep(0.4)
    raise RuntimeError(
        "GPT_WEB_SUBMIT_NOT_CONFIRMED:" + json.dumps(last,ensure_ascii=False,sort_keys=True)
    )


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
        # The composer must be present before upload; this also distinguishes a
        # logged-out/login-only surface from a usable ChatGPT conversation page.
        _focus_composer(page, timeout_seconds=12.0)

        element = page.call("Runtime.evaluate", {
            "expression": """(() => {
              const inputs = Array.from(document.querySelectorAll('input[type=file]'));
              return inputs.find(el => (el.accept || '').toLowerCase().includes('image'))
                || inputs.find(el => !(el.accept || '').trim())
                || null;
            })()""",
            "returnByValue": False,
        }).get("result") or {}
        object_id = element.get("objectId")
        if not object_id:
            raise RuntimeError(
                "GPT_WEB_FILE_INPUT_NOT_FOUND:" +
                json.dumps(_composer_snapshot(page), ensure_ascii=False, sort_keys=True)
            )
        page.call("DOM.setFileInputFiles", {"objectId": object_id, "files": [str(image)]})
        # CDP acknowledgement only confirms a browser operation; verify the
        # selected file on the exact input object before its DOM can rerender.
        selected = page.call("Runtime.callFunctionOn", {
            "objectId": object_id,
            "functionDeclaration": """function() {
              return Array.from(this.files || []).map(f => ({name:f.name,size:f.size,type:f.type}));
            }""",
            "returnByValue": True,
        }).get("result") or {}
        selected_files = selected.get("value") or []
        # React may replace the input synchronously after the change event.
        # In that case, the stale object can have an empty FileList even if
        # the application received the image. Classify as inconclusive rather
        # than asserting an upload failure; retain the later live reply gate.
        selection_confirmed = any(
            isinstance(f, dict) and f.get("name") == image.name
            and f.get("size") == image.stat().st_size
            for f in selected_files
        )
        if not selection_confirmed:
            # Upload previews can be asynchronous; a single immediate DOM
            # read is not evidence that the frontend rejected the image.
            upload_deadline = time.monotonic() + 8.0
            upload_observation: dict[str, Any] = {}
            while time.monotonic() < upload_deadline:
                upload_observation = _submission_snapshot(page, request_id)
                if int((upload_observation.get("attachmentSummary") or {}).get("imagePreviewCount") or 0) > 0:
                    selection_confirmed = True
                    break
                time.sleep(0.4)
            if not selection_confirmed:
                raise RuntimeError(
                    "GPT_WEB_FILE_SELECTION_UNVERIFIED:" +
                    json.dumps(upload_observation, ensure_ascii=False, sort_keys=True)
                )

        # File upload may rerender the composer. Reacquire/focus it instead of
        # assuming the pre-upload DOM node is still active.
        _focus_composer(page, timeout_seconds=12.0)
        prompt = str(inner["prompt"])
        baseline = _submission_snapshot(page, request_id)
        baseline_assistants = int(baseline.get("assistantCount") or 0)
        baseline_users = int(baseline.get("userCount") or 0)
        page.call("Input.insertText", {"text": prompt})

        inserted = _submission_snapshot(page, request_id)
        if inserted.get("composerHasRequest") is not True:
            raise RuntimeError(
                "GPT_WEB_PROMPT_INSERT_NOT_CONFIRMED:" +
                json.dumps(inserted, ensure_ascii=False, sort_keys=True)
            )

        _click_send(page, request_id=request_id, timeout_seconds=12.0)
        _confirm_submit(
            page,
            request_id=request_id,
            baseline_assistants=baseline_assistants,
            baseline_users=baseline_users,
            timeout_seconds=8.0,
        )

        deadline = time.monotonic() + 45
        last_snapshot: dict[str, Any] = {}
        saw_generation = False
        saw_correlated_user = False
        saw_assistant = False
        empty_message_ticks = 0
        while time.monotonic() < deadline:
            text = _assistant_text(page, request_id)
            if text:
                if len(text) > MAX_TEXT:
                    raise RuntimeError("GPT_WEB_RESPONSE_TOO_LARGE")
                return text
            last_snapshot = _submission_snapshot(page, request_id)
            saw_generation |= last_snapshot.get("generating") is True
            saw_correlated_user |= int(last_snapshot.get("correlatedUserCount") or 0) > 0
            saw_assistant |= int(last_snapshot.get("assistantCount") or 0) > baseline_assistants
            # A transient /uc/ route may use a different message renderer. If
            # generation finished but no role-bearing messages ever appeared,
            # return a precise incompatibility instead of a generic timeout.
            if (last_snapshot.get("pagePath") or "").startswith("/uc/") and (
                last_snapshot.get("generating") is not True
                and int(last_snapshot.get("messageNodes") or 0) == 0
                and saw_generation
            ):
                empty_message_ticks += 1
                if empty_message_ticks >= 6:
                    raise RuntimeError(
                        "GPT_WEB_ROUTE_MESSAGE_SURFACE_UNSUPPORTED:" +
                        json.dumps(last_snapshot, ensure_ascii=False, sort_keys=True)
                    )
            else:
                empty_message_ticks = 0
            if (
                int(last_snapshot.get("assistantCount") or 0) > baseline_assistants
                and last_snapshot.get("generating") is not True
                and last_snapshot.get("lastAssistantHasRequest") is not True
            ):
                raise RuntimeError(
                    "GPT_WEB_RESPONSE_UNCORRELATED:" +
                    json.dumps(last_snapshot, ensure_ascii=False, sort_keys=True)
                )
            time.sleep(0.5)
        # Preserve transition evidence: the final DOM alone can be empty after
        # ChatGPT navigates, rerenders, or discards a newly submitted message.
        last_snapshot["sawGenerationAfterSubmit"] = saw_generation
        last_snapshot["sawCorrelatedUserAfterSubmit"] = saw_correlated_user
        last_snapshot["sawAssistantAfterSubmit"] = saw_assistant
        # This final structural snapshot helps distinguish a changed page route
        # from stale selectors; no user/assistant content is logged.
        raise RuntimeError(
            "GPT_WEB_RESPONSE_TIMEOUT:" +
            json.dumps(last_snapshot, ensure_ascii=False, sort_keys=True)
        )
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
