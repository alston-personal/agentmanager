#!/usr/bin/env python3
"""
Mio Threads Intelligence and Post Feeding API (mio-intel-hub)
Port: 3003 (Registered in port_registry.json)
Provides:
  - GET  /healthz
  - POST /api/feed   (Ingests human-fed or crawler-fed Threads post URLs)
  - GET  /api/feed   (Lists candidates and review statuses)
"""

from __future__ import annotations

import html as html_lib
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Any

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

PORT = 3003
HOST = "127.0.0.1"

BASE_DATA_DIR = Path("/home/ubuntu/agent-data/personas/sunlake-milkcat")
CANDIDATES_FILE = BASE_DATA_DIR / "intel_candidates.json"

THREADS_POST_REGEX = re.compile(
    r"^/@(?P<user>[A-Za-z0-9._]+)/post/(?P<code>[A-Za-z0-9_-]+)/?$",
    re.IGNORECASE,
)
THREADS_SHORT_REGEX = re.compile(r"^/(?:post|t)/(?P<code>[A-Za-z0-9_-]+)/?$", re.IGNORECASE)
THREADS_SHARE_REGEX = re.compile(r"^/share/(?P<code>[A-Za-z0-9_-]+)/?$", re.IGNORECASE)
THREADS_HOSTS = {"threads.com", "www.threads.com", "threads.net", "www.threads.net"}

BASE64_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"


def shortcode_to_media_id(shortcode: str) -> str:
    """Converts a Threads Base64 shortcode into a numeric media_id / post_id."""
    media_id = 0
    for char in shortcode:
        idx = BASE64_ALPHABET.find(char)
        if idx == -1:
            raise ValueError(f"Invalid character in shortcode: {char}")
        media_id = (media_id * 64) + idx
    return str(media_id)


def media_id_to_shortcode(media_id: str | int) -> str:
    num = int(media_id)
    if num == 0:
        return "A"
    chars = []
    while num > 0:
        chars.append(BASE64_ALPHABET[num % 64])
        num //= 64
    return "".join(reversed(chars))


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_candidates() -> dict[str, Any]:
    default_payload: dict[str, Any] = {
        "schema": "agentos.mio-intel-candidates/v1",
        "updated_at": now_iso(),
        "candidates": [],
    }
    if not CANDIDATES_FILE.is_file():
        return default_payload
    try:
        content = json.loads(CANDIDATES_FILE.read_text(encoding="utf-8"))
        if not isinstance(content, dict) or "candidates" not in content:
            return default_payload
        return content
    except Exception:
        return default_payload


def save_candidates(data: dict[str, Any]) -> None:
    BASE_DATA_DIR.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = now_iso()
    temp_path = CANDIDATES_FILE.with_suffix(f".tmp.{os.getpid()}")
    temp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(CANDIDATES_FILE)


def fetch_threads_preview(canonical_url: str, shortcode: str, fallback_user: str = "") -> dict[str, str]:
    """
    Attempts to fetch OpenGraph metadata from the Threads URL using facebookexternalhit.
    Falls back gracefully to URL metadata if restricted or offline.
    """
    author = f"@{fallback_user}" if fallback_user else "Threads 用戶"
    text = ""
    title = ""

    req = urllib.request.Request(
        canonical_url,
        headers={
            "User-Agent": "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)",
            "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept": "text/html,application/xhtml+xml",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            content = resp.read(512_000).decode("utf-8", errors="replace")
            desc_match = re.search(r'<meta property="og:description" content="([^"]+)"', content)
            title_match = re.search(r'<meta property="og:title" content="([^"]+)"', content)

            if desc_match:
                raw_text = html_lib.unescape(desc_match.group(1)).strip()
                # Clean up login redirection text
                if not raw_text.startswith("Join Threads") and not raw_text.startswith("加入 Threads"):
                    text = raw_text

            if title_match:
                title = html_lib.unescape(title_match.group(1)).strip()
                # Extract author name from title e.g. "Name (@username) on Threads"
                author_match = re.search(r"^(.+?)(?:\s*\(@|\s*on Threads)", title)
                if author_match and author_match.group(1).strip():
                    author = author_match.group(1).strip()
    except Exception:
        pass

    return {
        "author": author,
        "title": title,
        "text": text,
    }


def parse_and_validate_url(raw_url: str) -> dict[str, str]:
    """A URL candidate is never a verified provider parent-ID receipt."""
    cleaned = (raw_url or "").strip()
    try:
        parsed = urllib.parse.urlsplit(cleaned)
        if (parsed.scheme != "https" or (parsed.hostname or "").lower() not in THREADS_HOSTS
                or parsed.username is not None or parsed.password is not None
                or parsed.port not in (None, 443) or parsed.query or parsed.fragment):
            raise ValueError("invalid Threads URL")
    except ValueError as exc:
        raise ValueError("請輸入有效的 Threads 貼文連結 (例如 https://www.threads.com/@username/post/...)") from exc

    direct = THREADS_POST_REGEX.fullmatch(parsed.path)
    legacy = THREADS_SHORT_REGEX.fullmatch(parsed.path)
    share = THREADS_SHARE_REGEX.fullmatch(parsed.path)
    match = direct or legacy or share
    if match is None:
        raise ValueError("請輸入有效的 Threads 貼文連結 (例如 https://www.threads.com/@username/post/...)")
    code = match.group("code")
    user = match.group("user") if direct else ""
    if share:
        # The actual permalink and author are resolved by the existing Reader.
        # Use a stable local candidate key, not a fabricated numeric media ID.
        return {"username": "", "shortcode": code, "media_id": "share:" + code,
                "canonical_url": "https://www.threads.com/share/" + code + "/",
                "id_provenance": "share_url_unresolved"}
    media_id = shortcode_to_media_id(code)
    canonical = "https://www.threads.com/" + ("@" + user + "/" if user else "") + "post/" + code
    return {"username": user, "shortcode": code, "media_id": media_id,
            "canonical_url": canonical, "id_provenance": "shortcode_derived_unverified"}


class MioIntelHandler(BaseHTTPRequestHandler):
    def _send_json(self, status_code: int, data: dict[str, Any]) -> None:
        raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Requested-With")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Requested-With")
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/")

        if path in ("/healthz", "/api/healthz"):
            self._send_json(200, {
                "ok": True,
                "status": "ok",
                "service": "mio-intel-hub",
                "port": PORT,
                "timestamp": now_iso(),
            })
            return

        if path in ("/api/feed", "/api/feed/"):
            query = urllib.parse.parse_qs(parsed.query)
            limit = int(query.get("limit", ["20"])[0])
            status_filter = query.get("status", [None])[0]

            store = load_candidates()
            candidates = store.get("candidates") or []

            # Compute summary stats
            stats = {
                "total": len(candidates),
                "pending_review": sum(1 for c in candidates if c.get("status") == "pending_review"),
                "scheduled": sum(1 for c in candidates if c.get("status") == "scheduled"),
                "replied": sum(1 for c in candidates if c.get("status") == "sent"),
                "passed_silence": sum(1 for c in candidates if c.get("status") == "passed_silence"),
            }

            filtered = candidates
            if status_filter:
                filtered = [c for c in candidates if c.get("status") == status_filter]

            # Return newest first
            filtered = list(reversed(filtered))[:limit]

            self._send_json(200, {
                "ok": True,
                "summary": stats,
                "candidates": filtered,
                "updated_at": store.get("updated_at"),
            })
            return

        self._send_json(404, {"ok": False, "error": "not_found"})

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/")

        if path in ("/api/feed", "/api/feed/"):
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length).decode("utf-8")
                payload = json.loads(body) if body else {}
            except Exception as e:
                self._send_json(400, {"ok": False, "error": f"invalid_json_payload: {e}"})
                return

            raw_url = str(payload.get("url") or "").strip()
            user_note = str(payload.get("note") or "").strip()
            source = str(payload.get("source") or "user_feeder").strip()

            if not raw_url:
                self._send_json(400, {"ok": False, "error": "請提供 Threads 貼文網址 (url)"})
                return

            try:
                url_info = parse_and_validate_url(raw_url)
            except ValueError as ve:
                self._send_json(400, {"ok": False, "error": str(ve)})
                return

            # Check existing candidates
            store = load_candidates()
            existing_list = store.setdefault("candidates", [])
            for c in existing_list:
                if c.get("id") == url_info["media_id"] or c.get("shortcode") == url_info["shortcode"]:
                    self._send_json(200, {
                        "ok": True,
                        "already_submitted": True,
                        "candidate": c,
                        "message": "這篇貼文之前已經投遞給澪囉！澪會在相應巡邏時間閱讀 🌸",
                    })
                    return

            # Fetch preview if not provided
            preview = fetch_threads_preview(
                url_info["canonical_url"],
                url_info["shortcode"],
                url_info["username"],
            )

            candidate: dict[str, Any] = {
                "id": url_info["media_id"],
                "id_provenance": url_info["id_provenance"],
                "reply_allowed": False,
                "shortcode": url_info["shortcode"],
                "username": url_info["username"],
                "url": url_info["canonical_url"],
                "author": preview.get("author") or (f"@{url_info['username']}" if url_info["username"] else "Threads 作者"),
                "title": preview.get("title") or "",
                "text": preview.get("text") or (f"[推薦備註]: {user_note}" if user_note else ""),
                "user_note": user_note,
                "source": source,
                "status": "pending_review",
                "created_at": now_iso(),
                "reviewed_at": None,
                "decision": None,
            }

            existing_list.append(candidate)
            save_candidates(store)

            self._send_json(201, {
                "ok": True,
                "already_submitted": False,
                "candidate": candidate,
                "message": "已成功投遞給澪！澪會在下次生活巡邏時閱讀並自主思考是否回覆 🌸",
            })
            return

        self._send_json(404, {"ok": False, "error": "not_found"})

    def log_message(self, format: str, *args: Any) -> None:
        # Standard silent logging to avoid noise, print errors only
        if args and str(args[1]) not in ("200", "201", "204"):
            sys.stderr.write(f"[mio-intel-hub] {self.address_string()} - {format % args}\n")


def run() -> None:
    server = HTTPServer((HOST, PORT), MioIntelHandler)
    print(f"[mio-intel-hub] Listening on http://{HOST}:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    run()
