from __future__ import annotations

import html as html_lib
import json
import re
import sys
import urllib.parse
import urllib.request
from html.parser import HTMLParser

ALLOWED_HOSTS = {"threads.net", "www.threads.net", "threads.com", "www.threads.com"}
MAX_BYTES = 768_000


class ThreadsSourceError(ValueError):
    pass


def _clean(value: str) -> str:
    value = html_lib.unescape(str(value or ""))
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def _valid_url(url: str) -> bool:
    try:
        p = urllib.parse.urlparse(str(url or "").strip())
    except Exception:
        return False
    if p.scheme != "https" or (p.hostname or "").lower() not in ALLOWED_HOSTS:
        return False
    return bool(re.search(r"/(?:@[^/]+/)?post/[^/?#]+|/t/[^/?#]+", p.path, re.I))


class _Parser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.meta = {}
        self.title = []
        self.in_title = False
        self.in_json_ld = False
        self.json_ld = []

    def handle_starttag(self, tag, attrs):
        attrs = {str(k).lower(): str(v or "") for k, v in attrs}
        tag = tag.lower()
        if tag == "meta":
            key = (attrs.get("property") or attrs.get("name") or "").lower()
            content = attrs.get("content", "").strip()
            if key and content and key not in self.meta:
                self.meta[key] = content
        elif tag == "title":
            self.in_title = True
        elif tag == "script" and attrs.get("type", "").lower() == "application/ld+json":
            self.in_json_ld = True

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag == "title":
            self.in_title = False
        elif tag == "script":
            self.in_json_ld = False

    def handle_data(self, data):
        if self.in_title:
            self.title.append(data)
        if self.in_json_ld:
            self.json_ld.append(data)


def _json_ld(parts):
    raw = "\n".join(parts).strip()
    if not raw:
        return "", ""
    try:
        payload = json.loads(raw)
    except Exception:
        return "", ""
    nodes = payload if isinstance(payload, list) else [payload]
    for node in nodes:
        if not isinstance(node, dict):
            continue
        text = node.get("articleBody") or node.get("text") or node.get("description") or ""
        author = node.get("author") or ""
        if isinstance(author, dict):
            author = author.get("name") or author.get("alternateName") or ""
        if text:
            return _clean(text), _clean(author)
    return "", ""


def _username(url: str) -> str:
    m = re.search(r"/@([^/]+)/post/", urllib.parse.urlparse(url).path, re.I)
    return m.group(1) if m else ""


def _author_from_title(title: str, username: str) -> str:
    title = _clean(title)
    for pattern in (
        r"^(.+?)\s*\(@[^)]+\)\s+on\s+Threads",
        r"^(.+?)\s+on\s+Threads",
        r"^(.+?)\s*[|·-]\s*Threads",
    ):
        m = re.search(pattern, title, re.I)
        if m:
            value = _clean(m.group(1)).strip('"“” ')
            if value:
                return value
    return f"@{username}" if username else "Threads 作者"


def parse_public_post_html(raw_html: str, source_url: str) -> dict:
    if not _valid_url(source_url):
        raise ThreadsSourceError("invalid_threads_url")
    parser = _Parser()
    parser.feed(raw_html)
    ld_text, ld_author = _json_ld(parser.json_ld)
    text = ld_text or parser.meta.get("og:description") or parser.meta.get("twitter:description") or parser.meta.get("description") or ""
    text = _clean(text)
    if not text:
        raise ThreadsSourceError("threads_post_text_unavailable")
    title = parser.meta.get("og:title") or parser.meta.get("twitter:title") or _clean("".join(parser.title))
    username = _username(source_url)
    author = ld_author or _author_from_title(title, username)
    return {
        "type": "threads",
        "author": _clean(author),
        "username": username,
        "text": text,
        "url": source_url,
    }


def resolve_public_post(url: str, timeout: float = 10.0) -> dict:
    url = str(url or "").strip()
    if not _valid_url(url):
        raise ThreadsSourceError("invalid_threads_url")
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; AgentOS-Threads/1.0; +https://milkcat.org/)",
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8,ja;q=0.7",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            final_url = resp.geturl()
            if not _valid_url(final_url):
                raise ThreadsSourceError("threads_redirect_not_allowed")
            raw = resp.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                raise ThreadsSourceError("threads_page_too_large")
            charset = resp.headers.get_content_charset() or "utf-8"
    except ThreadsSourceError:
        raise
    except Exception as exc:
        raise ThreadsSourceError("threads_fetch_failed") from exc
    return parse_public_post_html(raw.decode(charset, errors="replace"), final_url)


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 1:
        print(json.dumps({"ok": False, "error": "usage: social_threads.py <threads-url>"}, ensure_ascii=False))
        return 2
    try:
        data = resolve_public_post(argv[0])
        print(json.dumps({"ok": True, "source": data}, ensure_ascii=False))
        return 0
    except ThreadsSourceError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
