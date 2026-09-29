#!/usr/bin/env python3
from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request


def _raw_cdp_probe() -> dict:
    def get(url: str):
        with urllib.request.urlopen(url, timeout=5) as response:
            return json.load(response)

    version = get("http://127.0.0.1:9222/json/version")
    tabs = get("http://127.0.0.1:9222/json/list")
    threads = [t for t in tabs if "threads.com" in str(t.get("url") or "")]

    if not threads:
        target = "https://www.threads.com/messages"
        request = urllib.request.Request(
            "http://127.0.0.1:9222/json/new?" + urllib.parse.quote(target, safe=":/?=&"),
            method="PUT",
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            json.load(response)
        time.sleep(3)
        tabs = get("http://127.0.0.1:9222/json/list")
        threads = [t for t in tabs if "threads.com" in str(t.get("url") or "")]

    kinds = []
    urls = []
    for tab in threads:
        url = str(tab.get("url") or "")
        urls.append(url)
        if "/messages" in url:
            kinds.append("messages")
        elif "login" in url or "accounts" in url:
            kinds.append("login")
        else:
            kinds.append("threads_other")

    return {
        "schema": "agentos.social-session-probe/v0.2",
        "provider": "threads",
        "transport": "chrome-cdp",
        "cdp_ready": bool(version.get("webSocketDebuggerUrl")),
        "thread_tab_count": len(threads),
        "thread_kinds": sorted(kinds),
        "threads_urls": urls,
    }


def main() -> int:
    try:
        from agentos_node.macos_chrome_threads import inspect_threads_tabs
    except ModuleNotFoundError:
        result = _raw_cdp_probe()
    else:
        try:
            result = inspect_threads_tabs()
        except Exception:
            result = _raw_cdp_probe()
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
