#!/usr/bin/env python3
import html as html_lib
import json
import re
import sys
import time
import urllib.parse
import urllib.request

TERMS = ["抓漏", "冷氣清洗", "居家清潔", "家電維修", "驗屋"]
FILTERS = ["recent", "top"]
BASE = "https://www.threads.com/search/"
UA = "milkcat-vendor-public-search-probe/1.0"


def normalize_html(raw: str) -> str:
    value = html_lib.unescape(raw)
    value = value.replace("\\/", "/")
    value = value.replace("\\u002F", "/").replace("\\u002f", "/")
    return value


def extract_urls(raw: str):
    text = normalize_html(raw)
    found = set()
    patterns = [
        r"https://(?:www\.)?threads\.com/@[^\s\"'<>/]+/post/[A-Za-z0-9_-]+",
        r"href=[\"'](/@[^\"'<>/]+/post/[A-Za-z0-9_-]+)",
    ]
    for pattern in patterns:
        for match in re.findall(pattern, text):
            url = match if match.startswith("http") else "https://www.threads.com" + match
            url = url.split("?", 1)[0].rstrip("/")
            found.add(url)
    return sorted(found)


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
                urls = extract_urls(body)[:25]
                all_urls.update(urls)
                rows.append({
                    "term": term,
                    "filter": filter_name,
                    "mode": mode,
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
                    "http_status": None,
                    "final_host": None,
                    "result_count": 0,
                    "urls": [],
                    "error": type(exc).__name__,
                })
            time.sleep(0.4)

    print(json.dumps({
        "schema": "milkcat.threads-public-search-probe/v1",
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
