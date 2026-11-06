#!/usr/bin/env python3
"""
🏥 Web Surface Health Checker (定檢員巡檢核心)
定時探測 AgentOS 公開對外路由，若發現 403 / 404 / 502 等非 200 異常，
立刻回報並可自動阻斷/報警，確保生產線死鏈為 P0 最高優先級。
"""
import sys
import urllib.request
import urllib.error
import json
from datetime import datetime

CHECK_ROUTES = [
    {"url": "https://studio.milkcat.org/", "name": "Studio 首頁", "critical": True},
    {"url": "https://studio.milkcat.org/role-island/", "name": "Role-Island 觀測中心", "critical": True},
    {"url": "https://studio.milkcat.org/mission-control/", "name": "作戰指揮室", "critical": True},
    {"url": "https://studio.milkcat.org/personas/mio/", "name": "澪的生活活動紀錄", "critical": True},
    {"url": "https://studio.milkcat.org/personas/mio/activity.json", "name": "澪 Activity JSON", "critical": True},
    {"url": "https://studio.milkcat.org/tiandao/", "name": "天道連載小說首頁", "critical": True},
]

def check_endpoints():
    results = []
    has_failure = False

    for r in CHECK_ROUTES:
        req = urllib.request.Request(
            r["url"],
            headers={"User-Agent": "AgentOS-Sentinel-Inspector/1.0"}
        )
        status_code = 0
        error_msg = ""
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                status_code = resp.getcode()
        except urllib.error.HTTPError as e:
            status_code = e.code
            error_msg = str(e)
            has_failure = True
        except Exception as e:
            status_code = 0
            error_msg = str(e)
            has_failure = True

        is_ok = (status_code == 200)
        results.append({
            "name": r["name"],
            "url": r["url"],
            "status": status_code,
            "ok": is_ok,
            "error": error_msg,
            "critical": r["critical"]
        })

    print(json.dumps({
        "timestamp": datetime.now().isoformat(),
        "all_passed": not has_failure,
        "results": results
    }, ensure_ascii=False, indent=2))

    return 0 if not has_failure else 1

if __name__ == "__main__":
    sys.exit(check_endpoints())

