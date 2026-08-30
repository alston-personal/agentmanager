#!/usr/bin/env python3
import html as html_lib
import json
import re
import sys
import time
import urllib.parse
import urllib.request

UA = "milkcat-vendor-source-graph-probe/1.0"


def normalize_threads_post_url(value: str | None):
    if not value:
        return None
    value = html_lib.unescape(value).replace("\\/", "/").replace("\\u002F", "/").replace("\\u002f", "/")
    try:
        p = urllib.parse.urlsplit(value)
    except ValueError:
        return None
    if (p.hostname or "").lower() not in {"threads.com", "www.threads.com", "threads.net", "www.threads.net"}:
        return None
    path = p.path.rstrip("/")
    if not re.fullmatch(r"/@[^/]+/post/[A-Za-z0-9_-]+", path):
        return None
    return "https://www.threads.com" + path


def extract_post_urls(raw: str):
    text = html_lib.unescape(raw).replace("\\/", "/").replace("\\u002F", "/").replace("\\u002f", "/")
    found = set()

    for match in re.findall(r"https://(?:www\.)?threads\.(?:com|net)/@[^\s\"'<>/]+/post/[A-Za-z0-9_-]+", text):
        url = normalize_threads_post_url(match)
        if url:
            found.add(url)

    for match in re.findall(r"(?:href=)?[\"'](/@[^\"'<>/]+/post/[A-Za-z0-9_-]+)", text):
        url = normalize_threads_post_url("https://www.threads.com" + match)
        if url:
            found.add(url)

    # Threads embeds post objects in serialized page state. Probe only the
    # public username+post-code pair; do not emit captions or interaction data.
    for code_match in re.finditer(r'[\"\\]code[\"\\]\s*:\s*[\"\\]([A-Za-z0-9_-]+)', text):
        start = max(0, code_match.start() - 1800)
        end = min(len(text), code_match.end() + 1800)
        window = text[start:end]
        users = re.findall(r'[\"\\]username[\"\\]\s*:\s*[\"\\]([^\"\\]{1,80})', window)
        if not users:
            continue
        username = users[-1].strip()
        if not username or any(ch.isspace() for ch in username):
            continue
        url = normalize_threads_post_url(f"https://www.threads.com/@{username}/post/{code_match.group(1)}")
        if url:
            found.add(url)

    return sorted(found)


def fetch(url: str):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.5",
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.status, resp.geturl(), resp.read().decode("utf-8", "replace")


def read_sources(path: str):
    out = []
    for line in open(path, encoding="utf-8", errors="replace"):
        line = line.rstrip("\n\r")
        if not line:
            continue
        parts = line.split("\t")
        input_url = parts[0].strip()
        canonical_url = parts[1].strip() if len(parts) > 1 else ""
        chosen = canonical_url or input_url
        out.append({"input_url": input_url, "canonical_url": canonical_url or None, "fetch_url": chosen})
    return out


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: probe_vendor_source_link_graph.py <sources.tsv>")

    sources = read_sources(sys.argv[1])
    rows = []
    all_connected = set()
    root_urls = set()

    for source in sources:
        root = normalize_threads_post_url(source["canonical_url"] or source["input_url"])
        if root:
            root_urls.add(root)
        try:
            status, final_url, body = fetch(source["fetch_url"])
            final_post = normalize_threads_post_url(final_url)
            if final_post:
                root_urls.add(final_post)
            urls = extract_post_urls(body)
            connected = sorted(set(urls) - root_urls)
            all_connected.update(connected)
            rows.append({
                "input_url": source["input_url"],
                "canonical_url": source["canonical_url"],
                "http_status": status,
                "final_host": urllib.parse.urlsplit(final_url).hostname,
                "root_post_resolved": final_post is not None,
                "page_post_url_count": len(urls),
                "connected_post_url_count": len(connected),
                "connected_post_urls": connected[:50],
                "error": None,
            })
        except Exception as exc:
            rows.append({
                "input_url": source["input_url"],
                "canonical_url": source["canonical_url"],
                "http_status": None,
                "final_host": None,
                "root_post_resolved": False,
                "page_post_url_count": 0,
                "connected_post_url_count": 0,
                "connected_post_urls": [],
                "error": type(exc).__name__,
            })
        time.sleep(0.5)

    print(json.dumps({
        "schema": "milkcat.vendor-source-link-graph-probe/v1",
        "ok": len(sources) > 0 and all(row["error"] is None for row in rows),
        "active_sources": len(sources),
        "canonical_sources": sum(1 for s in sources if s["canonical_url"]),
        "unique_root_post_urls": len(root_urls),
        "unique_connected_post_urls": len(all_connected - root_urls),
        "sources": rows,
        "login_bypass_used": False,
        "anti_bot_bypass_used": False,
        "post_text_emitted": False,
        "token_used": False,
        "db_written": False,
        "candidate_promoted": False,
        "core_modified": False,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
