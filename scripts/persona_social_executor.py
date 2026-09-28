#!/usr/bin/env python3
import argparse, json, os, urllib.request, urllib.error
from datetime import datetime, timezone
from pathlib import Path

RUNTIME="http://127.0.0.1:8771"
ENV=Path("/home/ubuntu/.config/agentos/social-runtime.env")
CREDS=Path("/home/ubuntu/.local/state/agentos/social/credentials.json")

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
        try: data=json.loads(raw)
        except Exception: data={"ok":False,"error":raw[:500]}
        return e.code,data

def find_binding(creds,username):
    bindings=creds.get("bindings",{}) if isinstance(creds,dict) else {}
    candidates=[]
    for binding_id,item in bindings.items():
        if not isinstance(item,dict): continue
        if item.get("platform")!="threads": continue
        if str(item.get("username") or "").lower()==username.lower():
            candidates.append((binding_id,item))
    persona=[x for x in candidates if ":persona:" in x[0]]
    return (persona or candidates)[0] if (persona or candidates) else (None,None)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--persona-dir",required=True)
    ap.add_argument("--username",default="mio.milkcat")
    ap.add_argument("--receipt-out",required=True)
    args=ap.parse_args()
    root=Path(args.persona_dir)
    state=json.load(open(root/"pdca/state.json",encoding="utf-8"))
    pending=list(state.get("pending_external_actions") or [])
    target=next((x for x in pending if x.get("status")=="candidate" and x.get("capability")=="social.reply.review"),None)
    now=datetime.now(timezone.utc).isoformat().replace("+00:00","Z")
    if not target:
        result={"schema":"agentos.persona-social-executor-receipt/v1","ok":True,"status":"NO_ACTION","timestamp":now}
        Path(args.receipt_out).write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        print(json.dumps(result,ensure_ascii=False)); return 0

    env=parse_env(ENV)
    registry=json.loads(env["AGENTOS_SOCIAL_PRODUCTS_JSON"])
    product="galaxy"
    product_key=str(registry[product]["api_key"])
    creds=json.loads(CREDS.read_text(encoding="utf-8"))
    binding_id,binding=find_binding(creds,args.username)
    if not binding_id:
        raise SystemExit("persona_threads_binding_not_found")

    base={"schema":"agentos.social-request/v1","product_id":product,"platform":"threads","account_binding_id":binding_id}
    headers={"X-AgentOS-Product-Key":product_key}
    sc,posts_r=post("/v1/social/status",{**base,"operation":"post.read"},headers)
    if sc!=200 or posts_r.get("ok") is False:
        raise SystemExit("post_read_failed:"+str(posts_r.get("error") or sc))
    posts=(posts_r.get("result") or {}).get("items") or []

    observed=[]
    for p in posts[:20]:
        pid=str(p.get("id") or "")
        if not pid or p.get("has_replies") is False: continue
        rc,rr=post("/v1/social/status",{**base,"operation":"replies.read","object_id":pid},headers)
        if rc!=200 or rr.get("ok") is False: continue
        for item in ((rr.get("result") or {}).get("items") or []):
            if not item.get("id"): continue
            observed.append({
                "id":str(item.get("id")),
                "root_id":pid,
                "username":item.get("username"),
                "timestamp":item.get("timestamp"),
                "text":item.get("text"),
                "permalink":item.get("permalink"),
                "replied_to_id":((item.get("replied_to") or {}).get("id") if isinstance(item.get("replied_to"),dict) else None),
            })

    seen_ids=set()
    events_path=root/"events/events.jsonl"
    if events_path.exists():
        for line in events_path.read_text(encoding="utf-8").splitlines():
            try:
                e=json.loads(line)
                if e.get("source_object_id"): seen_ids.add(str(e["source_object_id"]))
            except Exception: pass
    fresh=[x for x in observed if x["id"] not in seen_ids]

    receipt={
      "schema":"agentos.persona-social-executor-receipt/v1","ok":True,"status":"EXECUTED",
      "timestamp":now,"persona_username":args.username,"capability":"social.reply.review",
      "account_binding_id":binding_id,"posts_scanned":len(posts[:20]),"replies_observed":len(observed),
      "fresh_replies":len(fresh),"items":fresh[:50],
      "source_receipts_verified":True,"write_performed":False
    }
    out=Path(args.receipt_out); out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

    with open(events_path,"a",encoding="utf-8") as f:
        for item in fresh:
            f.write(json.dumps({
              "id":"threads:reply:"+item["id"],"type":"reply.observed","timestamp":item.get("timestamp") or now,
              "source":"agentos_shared_social_capability","source_object_id":item["id"],"root_id":item["root_id"],
              "username":item.get("username"),"text":item.get("text"),"permalink":item.get("permalink"),
              "pdca_external_receipt":str(out.relative_to(root))
            },ensure_ascii=False,separators=(",",":"))+"\n")

    for x in pending:
        if x is target:
            x["status"]="executed"
            x["executed_at"]=now
            x["receipt_ref"]=str(out.relative_to(root))
            x["fresh_replies"]=len(fresh)
    state["pending_external_actions"]=pending[-12:]
    state["last_social_receipt"]=str(out.relative_to(root))
    tmp=root/"pdca/state.json.tmp"
    tmp.write_text(json.dumps(state,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    os.replace(tmp,root/"pdca/state.json")
    print(json.dumps(receipt,ensure_ascii=False))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
