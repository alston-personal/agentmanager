"""Read-only GUI tab inventory. URLs and cookies never leave Oracle."""
import json
import urllib.request
from urllib.parse import urlsplit

PORTS=(9222,9223,9224)
def inspect(opener=urllib.request.urlopen):
    results=[]
    for port in PORTS:
        result={"port":port,"cdp_reachable":False,"threads_tabs":0,
                "threads_home_tabs":0,"identity_verified":False}
        try:
            with opener("http://127.0.0.1:%d/json/list"%port,timeout=3) as response:
                tabs=json.loads(response.read(100000))
            if not isinstance(tabs,list):
                raise ValueError("invalid tabs")
            result["cdp_reachable"]=True
            for tab in tabs[:100]:
                if not isinstance(tab,dict) or tab.get("type")!="page":
                    continue
                url=tab.get("url")
                if not isinstance(url,str):
                    continue
                parsed=urlsplit(url)
                if parsed.scheme=="https" and parsed.hostname in ("www.threads.com","threads.com"):
                    result["threads_tabs"]+=1
                    if parsed.path in ("","/"):
                        result["threads_home_tabs"]+=1
        except (OSError,ValueError,TypeError,TimeoutError):
            pass
        results.append(result)
    return {"schema":"agentos.mio-gui-tab-inventory/v1","status":"TRANSPORT_ONLY",
            "ports":results,"identity_verified":False,"for_you_read_verified":False,
            "write_performed":False,"login_attempted":False,"cookies_accessed":False,
            "candidate_count":0}

if __name__=="__main__":
    print("mio_gui_tab_inventory_receipt="+json.dumps(inspect(),sort_keys=True))
