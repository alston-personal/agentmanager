"""Linux-capable Gemini Web relay for AgentOS.

The worker owns only browser/session automation. It does not own AgentOS task
lineage, ProjectState, cognitive truth, or browser credentials outside its
persistent profile directory. Playwright is an optional runtime dependency and
is imported lazily so deterministic AgentOS tests remain browser-free.
"""

from __future__ import annotations

from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
import json
from pathlib import Path
import threading
import time
from typing import Any, Mapping, Protocol
from urllib.parse import urlparse


PROVIDER_REQUEST_PROTOCOL = "agentos.provider-request/v1"
GEMINI_URL = "https://gemini.google.com/app"
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}

PROMPT_SELECTOR = ", ".join(
    (
        "div.ql-editor",
        'rich-textarea [contenteditable="true"]',
        '[aria-label="Enter a prompt here"]',
        '[contenteditable="true"][role="textbox"]',
    )
)
SEND_SELECTOR = ", ".join(
    (
        'button[aria-label="Send message"]',
        'button[aria-label*="Send" i]',
        ".send-button",
        "button.send-button",
    )
)
RESPONSE_SELECTOR = ", ".join(
    (
        "model-response",
        "message-content",
        ".model-response-text",
        ".response-content",
    )
)
STREAMING_SELECTOR = ', '.join(('[aria-busy="true"]', 'button[aria-label*="Stop" i]'))
SIGN_IN_SELECTOR = ", ".join(
    (
        'a[href*="accounts.google.com"]',
        'button:has-text("Sign in")',
        '[aria-label*="Sign in" i]',
    )
)


class GeminiWebError(RuntimeError):
    pass


class GeminiSession(Protocol):
    def ask(self, prompt: str, *, timeout_seconds: float = 180.0) -> str: ...


def parse_semantic_response(raw: str) -> dict[str, Any]:
    """Parse the provider JSON requested by AgentOS from visible Gemini text."""

    text = str(raw or "").strip()
    if text.lower().startswith("gemini said"):
        text = text[len("gemini said") :].strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise GeminiWebError(f"Gemini Web did not return valid AgentOS JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise GeminiWebError("Gemini Web semantic response must be a JSON object")
    if value.get("status") not in {"succeeded", "failed"}:
        raise GeminiWebError("Gemini Web response status must be succeeded or failed")
    if not isinstance(value.get("result"), dict):
        raise GeminiWebError("Gemini Web response result must be an object")
    return value


@dataclass
class PlaywrightGeminiSession:
    profile_dir: str
    browser_executable: str | None = None
    headless: bool = False
    start_url: str = GEMINI_URL
    settle_seconds: float = 1.5
    poll_seconds: float = 0.25

    def __post_init__(self) -> None:
        self._playwright = None
        self._context = None
        self._page = None
        self._lock = threading.Lock()

    def _ensure_page(self):
        if self._page is not None and not self._page.is_closed():
            return self._page
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:  # pragma: no cover - depends on live host
            raise GeminiWebError(
                "Playwright is not installed; install it only on the isolated browser worker host"
            ) from exc

        profile = Path(self.profile_dir).expanduser()
        if not profile.exists() or not profile.is_dir():
            raise GeminiWebError("persistent Gemini browser profile directory does not exist")

        self._playwright = sync_playwright().start()
        launch_args: dict[str, Any] = {
            "user_data_dir": str(profile),
            "headless": self.headless,
        }
        if self.browser_executable:
            launch_args["executable_path"] = self.browser_executable
        self._context = self._playwright.chromium.launch_persistent_context(**launch_args)
        pages = self._context.pages
        self._page = pages[0] if pages else self._context.new_page()
        self._page.goto(self.start_url, wait_until="domcontentloaded", timeout=60_000)
        return self._page

    @staticmethod
    def _last_text(page) -> str:
        blocks = page.locator(RESPONSE_SELECTOR)
        count = blocks.count()
        if count < 1:
            return ""
        return (blocks.nth(count - 1).inner_text(timeout=2_000) or "").strip()

    def _wait_for_reply(self, page, *, baseline_count: int, baseline_text: str, timeout_seconds: float) -> str:
        deadline = time.monotonic() + timeout_seconds
        last_text = ""
        stable_since: float | None = None

        while time.monotonic() < deadline:
            blocks = page.locator(RESPONSE_SELECTOR)
            count = blocks.count()
            text = self._last_text(page)
            changed = count > baseline_count or (text and text != baseline_text)
            streaming = page.locator(STREAMING_SELECTOR).first.is_visible(timeout=250)

            if changed and text:
                if text != last_text:
                    last_text = text
                    stable_since = time.monotonic()
                elif not streaming and stable_since is not None and time.monotonic() - stable_since >= self.settle_seconds:
                    return text
            time.sleep(self.poll_seconds)
        raise GeminiWebError("timed out waiting for Gemini Web response to settle")

    def ask(self, prompt: str, *, timeout_seconds: float = 180.0) -> str:
        prompt = str(prompt or "").strip()
        if not prompt:
            raise ValueError("prompt is required")
        with self._lock:
            page = self._ensure_page()
            # A visible sign-in surface means the persisted profile is not ready.
            try:
                if page.locator(SIGN_IN_SELECTOR).first.is_visible(timeout=750):
                    raise GeminiWebError("Gemini Web profile is not signed in")
            except GeminiWebError:
                raise
            except Exception:
                pass

            input_box = page.locator(PROMPT_SELECTOR).first
            if not input_box.is_visible(timeout=5_000):
                raise GeminiWebError("Gemini prompt input is not available")
            baseline_count = page.locator(RESPONSE_SELECTOR).count()
            baseline_text = self._last_text(page)
            input_box.fill(prompt)

            send = page.locator(SEND_SELECTOR).first
            if send.is_visible(timeout=1_500):
                send.click(timeout=5_000)
            else:
                input_box.press("Enter")
            return self._wait_for_reply(
                page,
                baseline_count=baseline_count,
                baseline_text=baseline_text,
                timeout_seconds=timeout_seconds,
            )


class GeminiWebRelay:
    """Translate AgentOS relay envelopes to one serialized Gemini Web session."""

    def __init__(self, session: GeminiSession, *, provider_id: str = "gemini-web-shadow") -> None:
        self.session = session
        self.provider_id = provider_id

    def invoke(self, envelope: Mapping[str, Any]) -> dict[str, Any]:
        if envelope.get("protocol") != PROVIDER_REQUEST_PROTOCOL:
            raise GeminiWebError("unsupported provider request protocol")
        requested_provider = envelope.get("provider_id")
        if requested_provider != self.provider_id:
            raise GeminiWebError("provider_id does not match this Gemini Web worker")
        instruction = envelope.get("instruction")
        if not isinstance(instruction, str) or not instruction.strip():
            raise GeminiWebError("provider instruction is required")
        raw = self.session.ask(instruction)
        return {"semantic_response": parse_semantic_response(raw)}


class GeminiWebRelayServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        server_address: tuple[str, int],
        relay: GeminiWebRelay,
        *,
        token: str | None = None,
    ) -> None:
        host = server_address[0]
        if host not in LOOPBACK_HOSTS and not token:
            raise ValueError("non-loopback Gemini Web worker requires a bearer token")
        self.relay = relay
        self.token = token
        super().__init__(server_address, _GeminiHandler)


class _GeminiHandler(BaseHTTPRequestHandler):
    server: GeminiWebRelayServer

    def log_message(self, format: str, *args: Any) -> None:  # pragma: no cover
        return

    def _send_json(self, status: int, payload: Mapping[str, Any]) -> None:
        raw = json.dumps(dict(payload), ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._send_json(200, {"ok": True, "provider_id": self.server.relay.provider_id})
            return
        self._send_json(404, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/v1/provider":
            self._send_json(404, {"error": "not_found"})
            return
        expected = self.server.token
        if expected:
            supplied = self.headers.get("Authorization", "")
            wanted = f"Bearer {expected}"
            if not hmac.compare_digest(supplied, wanted):
                self._send_json(401, {"error": "unauthorized"})
                return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 1 or length > 2_000_000:
                raise GeminiWebError("invalid request size")
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(payload, dict):
                raise GeminiWebError("request root must be an object")
            result = self.server.relay.invoke(payload)
        except (GeminiWebError, json.JSONDecodeError, ValueError) as exc:
            self._send_json(400, {"error": str(exc)})
            return
        except Exception:
            # Do not leak browser/session internals across the relay boundary.
            self._send_json(502, {"error": "gemini_web_worker_failed"})
            return
        self._send_json(200, result)
