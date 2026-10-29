"""Read-only local GUI Worker/Chromium transport inventory. No session or identity claims."""
import json
import urllib.request
from datetime import datetime, timezone

PORTS=(9222,9223,9224)
def inspect(opener=urllib.request.urlopen):
    found=[]
    for port in PORTS:
        item={"port":port,"cdp_reachable":False,"browser_protocol":False}
        try:
            request=urllib.request.Request("http://127.0.0.1:%d/json/version"%port)
            with opener(request,timeout=2) as response:
                d=json.loads(response.read(8192))
            if isinstance(d,dict) and isinstance(d.get("Browser"),str):
                item.update(cdp_reachable=True,browser_protocol=("Protocol-Version" in d))
        except (OSError,ValueError,TypeError,TimeoutError):
            pass
        found.append(item)
    return {"schema":"agentos.mio-gui-preflight/v1","checked_at":datetime.now(timezone.utc).isoformat(),
            "status":"TRANSPORT_ONLY" if any(x["cdp_reachable"] for x in found) else "BLOCKED",
            "reason":"IDENTITY_NOT_VERIFIED" if any(x["cdp_reachable"] for x in found) else "NO_LOCAL_CDP",
            "ports":found,"identity_verified":False,"for_you_read_verified":False,
            "candidate_count":0,"write_performed":False,"login_attempted":False,
            "anti_bot_bypass_used":False}

if __name__=="__main__":
    print("mio_gui_worker_preflight_receipt="+json.dumps(inspect(),sort_keys=True))
