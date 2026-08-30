#!/usr/bin/env python3
import html as html_lib
import json
import re
import time
import urllib.parse
import urllib.request

TERMS = ["抓漏", "冷氣清洗", "居家清潔", "家電維修", "驗屋"]
FILTERS = ["recent", "top"]
BASE = "https://www.threads.com/search/"
UA = "milkcat-vendor-public-search-probe/1.1"


def normalize_html(raw: str) -> str:
    value = html_lib.unescape(raw)
    value = value.replace("\\/", "/")
    value = value.replace("\\u002F", "/").replace("\\u002f", "/")
    return value


def balanced_json_object(text: str, start: int):
    depth = 0
    in_string = False
    escaped = False
    for pos in range(start, len(text)):
        ch = text[pos]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start:pos + 1]
    return None


def extract_ssr_urls(raw: str):
    text = normalize_html(raw)
    needle = '"searchResults":{"inform_module"'
    idx = text.find(needle)
    if idx < 0:
        return [], False
    prefix = '"searchResults":'
    start = text.find("{", idx + len(prefix))
    if start < 0:
        return [], True
    fragment = balanced_json_object(text, start)
    if not fragment:
        return [], True
    payload = json.loads(fragment)
    urls = set()
    for edge in payload.get("edges") or []:
        thread = ((edge.get("node") or {}).get("thread") or {})
        items = thread.get("thread_items") or []
        if not items:
            continue
        post = (items[0] or {}).get("post") or {}
        user = post.get("user") or {}
        username = (user.get("username") or "").strip()
        code = (post.get("code") or "").strip()
        if username and code:
            urls.add(f"https://www.threads.com/@{username}/post/{code}")
    return sorted(urls), True


def extract_regex_urls(raw: str):
    text = normalize_html(raw)
    found = set()
    patterns = [
        r"https://(?:www\.)?threads\.com/@[^\s\"'<>/]+/post/[A-Za-z0-9_-]+",
        r"href=[\"'](/@[^\"'<>/]+/post/[A-Za-z0-9_-]+)",
    ]
    for pattern in patterns:
        for match in re.findall(pattern, text):
            url = match if match.startswith("http") else "https://www.threads.com" + match
            found.add(url.split("?", 1)[0].rstrip("/"))
    return sorted(found)


def extract_urls(raw: str):
    ssr_urls, marker_found = extract_ssr_urls(raw)
    if ssr_urls:
        return ssr_urls, "ssr_json", marker_found
    regex_urls = extract_regex_urls(raw)
    return regex_urls, "regex", marker_found


def fetch_urllib(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.5"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.status, resp.geturl(), resp.read().decode("utf-8", "replace")


def playwright_available():
    try:
        import playwright.sync_api  # noqa: F401
        return True
    except Exception:
        return False


def fetch_playwright(url: str):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(locale="zh-TW", user_agent=UA)
        response = page.goto(url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2500)
        body = page.content()
        final_url = page.url
        status = response.status if response else None
        browser.close()
        return status, final_url, body


def main():
    use_playwright = playwright_available()
    rows = []
    all_urls = set()
    for term in TERMS:
        for filter_name in FILTERS:
            query = urllib.parse.urlencode({"q": term, "serp_type": filter_name})
            url = BASE + "?" + query
            mode = "playwright" if use_playwright else "urllib"
            try:
                if use_playwright:
                    status, final_url, body = fetch_playwright(url)
                else:
                    status, final_url, body = fetch_urllib(url)
                urls, parser, marker_found = extract_urls(body)
                urls = urls[:25]
                all_urls.update(urls)
                rows.append({
                    "term": term,
                    "filter": filter_name,
                    "mode": mode,
                    "parser": parser,
                    "search_results_marker_found": marker_found,
                    "http_status": status,
                    "final_host": urllib.parse.urlsplit(final_url).hostname,
                    "result_count": len(urls),
                    "urls": urls,
                    "error": None,
                })
            except Exception as exc:
                rows.append({
                    "term": term,
                    "filter": filter_name,
                    "mode": mode,
                    "parser": None,
                    "search_results_marker_found": False,
                    "http_status": None,
                    "final_host": None,
                    "result_count": 0,
                    "urls": [],
                    "error": type(exc).__name__,
                })
            time.sleep(0.4)

    print(json.dumps({
        "schema": "milkcat.threads-public-search-probe/v2",
        "ok": any(row["result_count"] > 0 for row in rows),
        "playwright_available": use_playwright,
        "queries": len(rows),
        "unique_post_urls": len(all_urls),
        "results": rows,
        "login_bypass_used": False,
        "anti_bot_bypass_used": False,
        "post_text_emitted": False,
        "token_used": False,
        "db_written": False,
        "core_modified": False,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
