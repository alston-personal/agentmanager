#!/usr/bin/env python3
import argparse, hashlib, json, urllib.request, urllib.error
from datetime import datetime, timezone
from pathlib import Path

RUNTIME="http://127.0.0.1:8771"
ENV=Path("/home/ubuntu/.config/agentos/social-runtime.env")
CREDS=Path("/home/ubuntu/.local/state/agentos/social/credentials.json")
KNOWN=("views","view_count","reach","impressions","likes","like_count","replies","reply_count","reposts","repost_count","quotes","quote_count","shares","share_count")

def parse_env(path):
    out={}
    for line in path.read_text(encoding="utf-8").splitlines():
        line=line.strip()
        if not line or line.startswith("#") or "=" not in line: continue
        k,v=line.split("=",1); v=v.strip()
        if len(v)>=2 and v[0] in ("'",'"') and v[-1]==v[0]: v=v[1:-1]
        out[k]=v
    return out

def post(path,payload,headers):
    body=json.dumps(payload,ensure_ascii=False).encode()
    req=urllib.request.Request(RUNTIME+path,data=body,headers={"content-type":"application/json","accept":"application/json",**headers},method="POST")
    try:
        with urllib.request.urlopen(req,timeout=20) as r:
            return r.status,json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raw=e.read().decode("utf-8","replace")
        try:data=json.loads(raw)
        except Exception:data={"ok":False,"error":raw[:400]}
        return e.code,data
    except Exception as e:
        return 0,{"ok":False,"error":type(e).__name__}

def binding(creds,username):
    items=[]
    for bid,item in (creds.get("bindings",{}) or {}).items():
        if not isinstance(item,dict) or item.get("platform")!="threads": continue
        if str(item.get("username") or "").lower()==username.lower(): items.append((bid,item))
    p=[x for x in items if ":persona:" in x[0]]
    return (p or items)[0] if (p or items) else (None,None)

def read_events(path):
    out=[]
    if not path.exists(): return out
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            x=json.loads(line)
            if isinstance(x,dict):out.append(x)
        except Exception:pass
    return out

def metrics_from(v):
    out={}
    def walk(x):
        if isinstance(x,dict):
            for k,val in x.items():
                lk=str(k).lower()
                if lk in KNOWN and isinstance(val,(int,float)) and not isinstance(val,bool):
                    out[lk]=val
                elif isinstance(val,(dict,list)): walk(val)
        elif isinstance(x,list):
            for y in x: walk(y)
    walk(v)
    return out

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--persona-dir",required=True)
    ap.add_argument("--username",default="mio.milkcat")
    ap.add_argument("--receipt-out",required=True)
    args=ap.parse_args()
    root=Path(args.persona_dir)
    events_path=root/"events/events.jsonl"
    events=read_events(events_path)
    now=datetime.now(timezone.utc).isoformat().replace("+00:00","Z")
    own=[]
    seen=set()
    for e in reversed(events):
        if e.get("type") not in ("post.sent","post.published"): continue
        oid=str(e.get("source_object_id") or e.get("object_id") or "")
        if not oid or oid in seen: continue
        seen.add(oid); own.append((oid,e))
        if len(own)>=8: break
    env=parse_env(ENV)
    try:
        registry=json.loads(env["AGENTOS_SOCIAL_PRODUCTS_JSON"])
        key=str(registry["galaxy"]["api_key"])
        creds=json.loads(CREDS.read_text(encoding="utf-8"))
    except Exception:
        result={"schema":"agentos.persona-growth-metrics-receipt/v1","ok":True,"status":"UNAVAILABLE","timestamp":now,"reason":"social_runtime_config_unavailable","changed":0}
        Path(args.receipt_out).parent.mkdir(parents=True,exist_ok=True); Path(args.receipt_out).write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
        print(json.dumps(result,ensure_ascii=False)); return 0
    bid,b=binding(creds,args.username)
    if not bid:
        result={"schema":"agentos.persona-growth-metrics-receipt/v1","ok":True,"status":"UNAVAILABLE","timestamp":now,"reason":"threads_binding_missing","changed":0}
        Path(args.receipt_out).parent.mkdir(parents=True,exist_ok=True); Path(args.receipt_out).write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
        print(json.dumps(result,ensure_ascii=False)); return 0
    base={"schema":"agentos.social-request/v1","product_id":"galaxy","platform":"threads","account_binding_id":bid}
    headers={"X-AgentOS-Product-Key":key}
    latest={}
    for e in events:
        if e.get("type")=="post.insights.observed":
            latest[str(e.get("post_object_id") or "")]=e.get("metrics") or {}
    changed=[]
    unsupported=0
    for oid,e in own:
        sc,res=post("/v1/social/status",{**base,"operation":"post.insights.read","object_id":oid},headers)
        if sc!=200 or res.get("ok") is False:
            unsupported+=1; continue
        m=metrics_from(res.get("result") or {})
        if not m: continue
        if m==latest.get(oid): continue
        snap=hashlib.sha256(json.dumps(m,sort_keys=True,separators=(",",":")).encode()).hexdigest()[:12]
        changed.append({"post_object_id":oid,"metrics":m,"snapshot":snap,"post_timestamp":e.get("timestamp")})
    if changed:
        with open(events_path,"a",encoding="utf-8") as f:
            for item in changed:
                f.write(json.dumps({
                  "schema":"agentos.persona-event/v1",
                  "event_id":"threads-insights-"+item["post_object_id"]+"-"+item["snapshot"],
                  "timestamp":now,"observed_at":now,"type":"post.insights.observed",
                  "platform":"threads","actor":"sunlake-milkcat-ai-001",
                  "post_object_id":item["post_object_id"],"post_timestamp":item.get("post_timestamp"),
                  "metrics":item["metrics"],"source":"AgentOS Shared Social Runtime post.insights.read",
                  "execution_origin":"read_only_growth_metrics"
                },ensure_ascii=False,separators=(",",":"))+"\n")
    result={"schema":"agentos.persona-growth-metrics-receipt/v1","ok":True,
            "status":"UPDATED" if changed else ("UNAVAILABLE" if unsupported==len(own) and own else "NO_CHANGE"),
            "timestamp":now,"posts_checked":len(own),"changed":len(changed),"unsupported":unsupported,
            "items":changed}
    out=Path(args.receipt_out); out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False)); return 0

if __name__=="__main__": raise SystemExit(main())
