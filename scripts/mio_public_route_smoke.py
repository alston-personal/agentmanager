#!/usr/bin/env python3
"""Read-only public Mio routes and activity projection diagnostic for issue #1707.

This script intentionally does not change production, read authentication cookies,
or infer that missing activity data means zero activity.
"""
import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

ROUTES = {
    "/personas/mio/": ("text/html", ("澪", "/personas/mio/wardrobe/")),
    "/personas/mio/wardrobe/": ("text/html", ("試穿",)),
    "/personas/mio/observer/": ("text/html", ("澪的內心窗口", "/personas/mio/")),
    "/personas/mio/activity.json": ("application/json", ()),
}

def probe(base, path, timeout):
    url = base.rstrip("/") + path
    request = urllib.request.Request(url, headers={
        "User-Agent": "agentos-mio-route-smoke/1.0",
        "Accept": "application/json,text/html",
        "Cache-Control": "no-cache",
    })
    result = {"path": path, "url": url, "ok": False}
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = response.status
            final_url = response.geturl()
            ctype = response.headers.get("Content-Type", "").split(";")[0].strip().lower()
            body = response.read(2_000_000).decode("utf-8", errors="replace")
        expected_type, markers = ROUTES[path]
        matches = {marker: marker in body for marker in markers}
        result.update(status=status, final_url=final_url, content_type=ctype, markers=matches)
        result["ok"] = (status == 200 and ctype == expected_type
                        and urllib.parse.urlsplit(final_url).path.rstrip("/") == path.rstrip("/")
                        and all(matches.values()))
        if path.endswith(".json") and status == 200 and ctype == "application/json":
            data = json.loads(body)
            result["json_is_object"] = isinstance(data, dict)
            result["activity_count_present"] = isinstance(data, dict) and "activity_count" in data
            result["updated_label_present"] = isinstance(data, dict) and bool(data.get("updated_label"))
            result["recent_is_array"] = isinstance(data, dict) and isinstance(data.get("recent"), list)
            result["ok"] = result["ok"] and result["json_is_object"] and result["recent_is_array"]
            # A count of zero is NOT proof of inactivity; never convert network failures into zero.
        return result
    except (urllib.error.URLError, ValueError, TimeoutError, json.JSONDecodeError) as exc:
        result["error_type"] = type(exc).__name__
        result["error"] = str(exc)[:300]
        return result

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--base-url", default="https://studio.milkcat.org")
    p.add_argument("--timeout", type=float, default=12.0)
    args = p.parse_args()
    parsed = urllib.parse.urlsplit(args.base_url)
    if parsed.scheme != "https" or not parsed.hostname:
        p.error("HTTPS base-url required")
    report = {
        "schema": "agentos.mio.public-route-smoke/v1",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "base_url": args.base_url,
        "routes": [probe(args.base_url, path, args.timeout) for path in ROUTES],
    }
    report["status"] = "PASS" if all(r["ok"] for r in report["routes"]) else "FAIL"
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1

if __name__ == "__main__":
    sys.exit(main())
