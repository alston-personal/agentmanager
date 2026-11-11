from __future__ import annotations

import html as html_lib
import json
import re
import urllib.parse
import urllib.request
from html.parser import HTMLParser

ALLOWED_HOSTS = {"threads.net", "www.threads.net", "threads.com", "www.threads.com"}
MAX_BYTES = 768_000
POST_PATH = re.compile(r"/(?:@([^/]+)/)?post/([^/?#]+)|/t/([^/?#]+)", re.I)


class ThreadsPublicReadError(ValueError):
    pass


def normalize_url(value: str) -> str:
    try:
        parsed = urllib.parse.urlsplit(str(value or "").strip())
    except ValueError as exc:
        raise ThreadsPublicReadError("invalid_threads_url") from exc
    if parsed.scheme != "https" or (parsed.hostname or "").lower() not in ALLOWED_HOSTS:
        raise ThreadsPublicReadError("invalid_threads_url")
    if not POST_PATH.fullmatch(parsed.path.rstrip("/")):
        raise ThreadsPublicReadError("invalid_threads_url")
    return urllib.parse.urlunsplit(("https", "www.threads.com", parsed.path.rstrip("/"), "", ""))


SHARE_PATH = re.compile(r"/share/[A-Za-z0-9_-]+", re.I)


def resolve_input_url(value: str, timeout: float = 10.0) -> str:
    """Canonicalize a public post or tightly bounded Threads share redirect."""
    try:
        parsed = urllib.parse.urlsplit(str(value or "").strip())
        if (parsed.scheme != "https" or (parsed.hostname or "").lower() not in ALLOWED_HOSTS
                or parsed.username or parsed.password or parsed.port not in (None, 443)
                or len(value) > 2048):
            raise ThreadsPublicReadError("invalid_threads_url")
    except (ValueError, TypeError) as exc:
        raise ThreadsPublicReadError("invalid_threads_url") from exc

    if not SHARE_PATH.fullmatch(parsed.path.rstrip("/")):
        return normalize_url(value)

    class ThreadsOnlyRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, request, fp, code, msg, headers, newurl):
            dest = urllib.parse.urlsplit(newurl)
            if (dest.scheme != "https" or (dest.hostname or "").lower() not in ALLOWED_HOSTS
                    or dest.username or dest.password or dest.port not in (None, 443)):
                raise ThreadsPublicReadError("unsafe_threads_redirect")
            return super().redirect_request(request, fp, code, msg, headers, newurl)

    try:
        opener = urllib.request.build_opener(ThreadsOnlyRedirect())
        request = urllib.request.Request(value, headers={"User-Agent": "AgentOS-Social/1.0"})
        with opener.open(request, timeout=timeout) as response:
            canonical = normalize_url(response.geturl())
            response.read(1)
        return canonical
    except ThreadsPublicReadError:
        raise
    except Exception as exc:
        raise ThreadsPublicReadError("threads_share_resolution_failed") from exc


class _Parser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, str] = {}
        self.json_ld: list[str] = []
        self._json_ld = False

    def handle_starttag(self, tag, attrs):
        values = {str(k).lower(): str(v or "") for k, v in attrs}
        if tag.lower() == "meta":
            key = (values.get("property") or values.get("name") or "").lower()
            if key and values.get("content") and key not in self.meta:
                self.meta[key] = values["content"]
        if tag.lower() == "script" and values.get("type", "").lower() == "application/ld+json":
            self._json_ld = True

    def handle_endtag(self, tag):
        if tag.lower() == "script":
            self._json_ld = False

    def handle_data(self, data):
        if self._json_ld:
            self.json_ld.append(data)


def _clean(value: str) -> str:
    value = html_lib.unescape(str(value or "")).replace("\r", "\n")
    value = re.sub(r"[ \t]+", " ", value)
    return re.sub(r"\n{3,}", "\n\n", value).strip()


def parse_public_post_html(raw_html: str, source_url: str) -> dict[str, str]:
    canonical = normalize_url(source_url)
    parser = _Parser()
    parser.feed(raw_html)
    text = ""
    author = ""
    raw_ld = "\n".join(parser.json_ld).strip()
    if raw_ld:
        try:
            payload = json.loads(raw_ld)
            nodes = payload if isinstance(payload, list) else [payload]
            for node in nodes:
                if not isinstance(node, dict):
                    continue
                text = _clean(node.get("articleBody") or node.get("text") or node.get("description") or "")
                raw_author = node.get("author") or ""
                if isinstance(raw_author, dict):
                    raw_author = raw_author.get("name") or raw_author.get("alternateName") or ""
                author = _clean(raw_author)
                if text:
                    break
        except (ValueError, TypeError):
            pass
    text = text or _clean(parser.meta.get("og:description") or parser.meta.get("description") or "")
    if not text:
        raise ThreadsPublicReadError("threads_post_text_unavailable")
    match = re.search(r"/@([^/]+)/post/", canonical, re.I)
    username = match.group(1) if match else ""
    return {"type": "threads", "author": author or (f"@{username}" if username else "Threads 作者"), "username": username, "text": text[:12000], "url": canonical}


def resolve_public_post(url: str, timeout: float = 10.0) -> dict[str, str]:
    canonical = resolve_input_url(url, timeout=timeout)
    request = urllib.request.Request(canonical, headers={"User-Agent": "AgentOS-Social/1.0", "Accept": "text/html,application/xhtml+xml"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            final_url = normalize_url(response.geturl())
            raw = response.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                raise ThreadsPublicReadError("threads_page_too_large")
            charset = response.headers.get_content_charset() or "utf-8"
    except ThreadsPublicReadError:
        raise
    except Exception as exc:
        raise ThreadsPublicReadError("threads_fetch_failed") from exc
    return parse_public_post_html(raw.decode(charset, errors="replace"), final_url)
