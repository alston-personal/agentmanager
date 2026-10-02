#!/usr/bin/env python3
import argparse, json, os, urllib.request, urllib.error
from datetime import datetime, timedelta, timezone
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
        if item.get("platform")!="threads" or item.get("product_id")!="galaxy": continue
        if item.get("auth_profile","persona")!="persona": continue
        if str(item.get("username") or "").lower()==username.lower():
            candidates.append((binding_id,item))
    persona=[x for x in candidates if ":persona:" in x[0]]
    ids={str(x[1].get("provider_account_id") or "") for x in candidates}
    if len(ids)!=1 or not next(iter(ids), ""):
        return None,None
    return (persona or candidates)[-1] if (persona or candidates) else (None,None)


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp=path.with_suffix(path.suffix+".tmp")
    tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    os.replace(tmp,path)


def timestamp(value):
    try:
        dt=datetime.fromisoformat(str(value).replace("Z","+00:00"))
        return dt.astimezone(timezone.utc) if dt.tzinfo else None
    except (ValueError,TypeError):
        return None


def read_items(request, headers):
    code, receipt=post("/v1/social/status",request,headers)
    if code!=200 or not isinstance(receipt,dict) or receipt.get("ok") is not True:
        raise RuntimeError("adapter_read_failed")
    result=receipt.get("result")
    if not isinstance(result,dict) or not isinstance(result.get("items"),list):
        raise RuntimeError("adapter_receipt_invalid")
    return result["items"], receipt


def observe(root, state, target, out, username, base, headers, now_dt):
    """A PDCA-authorized public read. DM and social writes are separate lanes."""
    action_id=target.get("action_id")
    cycle=target.get("cycle")
    if not isinstance(action_id,str) or not action_id or not isinstance(cycle,int) or cycle<1:
        raise RuntimeError("observation_intent_invalid")
    posts, posts_receipt=read_items({**base,"operation":"post.read"},headers)
    rows={}; receipts=[]; scanned=0
    for index, item in enumerate(posts[:20]):
        if not isinstance(item,dict) or not str(item.get("id") or "").isdigit():
            raise RuntimeError("owned_post_invalid")
        # Provider has_replies can lag. Always read the newest five posts.
        if index>=5 and item.get("has_replies") is False:
            continue
        pid=str(item["id"])
        replies, adapter=read_items({**base,"operation":"replies.read","object_id":pid},headers)
        scanned+=1
        receipts.append({"operation":"replies.read","object_id":pid,"ok":True,
                         "receipt_id":adapter.get("receipt_id")})
        for reply in replies:
            if not isinstance(reply,dict) or not str(reply.get("id") or "").isdigit():
                raise RuntimeError("reply_receipt_invalid")
            rid=str(reply["id"])
            rows[rid]={"id":rid,"root_id":pid,"username":reply.get("username"),
                       "timestamp":reply.get("timestamp"),"text":reply.get("text"),
                       "permalink":reply.get("permalink"),
                       "is_reply_owned_by_me":reply.get("is_reply_owned_by_me") is True,
                       "replied_to_id":(reply.get("replied_to") or {}).get("id")
                           if isinstance(reply.get("replied_to"),dict) else None}
    # Advance no cursor and emit no events until every required read has passed.
    previous=state.get("social_observation_cursor") or {}
    seen=set(str(x) for x in previous.get("seen_reply_ids",[]))
    events_path=root/"events/events.jsonl"
    if events_path.exists():
        for line in events_path.read_text(encoding="utf-8").splitlines():
            try:
                event=json.loads(line)
                if event.get("type")=="reply.observed" and event.get("source_object_id"):
                    seen.add(str(event["source_object_id"]))
            except (ValueError,TypeError,AttributeError):
                continue
    fresh=[row for rid,row in rows.items() if rid not in seen]
    eligible=[row for row in fresh if not row["is_reply_owned_by_me"]
              and str(row.get("username") or "").lstrip("@").lower()!=username.lstrip("@").lower()
              and timestamp(row.get("timestamp")) is not None
              and now_dt-timedelta(hours=42)<=timestamp(row["timestamp"])<=now_dt]
    observed_at=now_dt.isoformat().replace("+00:00","Z")
    ref=str(out.relative_to(root))
    result="NEW_REPLIES" if eligible else "NO_NEW_REPLIES"
    receipt={"schema":"agentos.persona-social-executor-receipt/v1","ok":True,
             "status":"EXECUTED","read_status":"PASS","result":result,
             "timestamp":observed_at,"observed_at":observed_at,"action_id":action_id,
             "cycle":cycle,"capability":target["capability"],"write_performed":False,
             "posts_scanned":scanned,"replies_observed":len(rows),"fresh_replies":len(eligible),
             "items":eligible,"source_receipts_verified":True,
             "adapter_receipts":[{"operation":"post.read","ok":True,
                                  "receipt_id":posts_receipt.get("receipt_id")},*receipts],
             "executor":"oracle-local-persona-social-lane",
             "cursor":{"previous_observed_at":previous.get("observed_at"),
                       "observed_at":observed_at,"seen_count":len(seen|set(rows))},
             "freshness":{"eligible_reply_max_age_hours":42}}
    save(out,receipt)
    with events_path.open("a",encoding="utf-8") as fh:
        for row in eligible:
            fh.write(json.dumps({"id":"threads:reply:"+row["id"],"type":"reply.observed",
                      "timestamp":row["timestamp"],"observed_at":observed_at,
                      "source":"agentos_shared_social_capability","source_object_id":row["id"],
                      "root_id":row["root_id"],"username":row["username"],"text":row["text"],
                      "permalink":row["permalink"],"replied_to_id":row["replied_to_id"],
                      "pdca_action_id":action_id,"pdca_external_receipt":ref},
                      ensure_ascii=False,separators=(",",":"))+"\n")
    target.update(status="completed",executed_at=observed_at,receipt_ref=ref,
                  read_status="PASS",fresh_replies=len(eligible))
    state["social_observation_cursor"]={"observed_at":observed_at,
        "seen_reply_ids":sorted(seen|set(rows))[-2000:]}
    summary={k:receipt[k] for k in ("action_id","cycle","capability","observed_at",
        "read_status","result","posts_scanned","replies_observed","fresh_replies","cursor","executor")}
    summary["receipt_ref"]=ref
    state["last_social_observation"]=summary
    state["last_social_receipt"]=ref
    pending=state.get("pending_external_actions") or []
    if eligible and target["capability"]=="social.threads.observe":
        review=next((x for x in pending if isinstance(x,dict)
            and x.get("capability")=="social.reply.review"
            and x.get("status") in ("candidate","in_progress")),None)
        if review is None:
            review={"action_id":f"mio-pdca-c{cycle}-social-reply-review","cycle":cycle,
                    "capability":"social.reply.review","status":"candidate",
                    "policy":"public_conversation=autonomous_with_policy",
                    "requires_real_adapter_receipt":True}
            pending.append(review)
        review["observation_receipt_ref"]=ref
        review["reply_ids"]=list(dict.fromkeys([*(review.get("reply_ids") or []),
                                              *(row["id"] for row in eligible)]))
    state["pending_external_actions"]=pending[-12:]
    save(root/"pdca/state.json",state)
    return receipt


def blocked_observation(root,state,target,out,now):
    # Exception text/provider envelopes may contain credentials: never copy them.
    ref=str(out.relative_to(root))
    receipt={"schema":"agentos.persona-social-executor-receipt/v1","ok":False,
        "status":"BLOCKED","read_status":"FAILED","result":"SOCIAL_ADAPTER_UNAVAILABLE",
        "timestamp":now,"observed_at":now,"action_id":target.get("action_id"),
        "cycle":target.get("cycle"),"capability":target.get("capability"),
        "write_performed":False,"source_receipts_verified":False,"receipt_ref":ref}
    save(out,receipt)
    target.update(status="blocked",receipt_ref=ref,blocked_at=now)
    state["last_social_observation"]=receipt
    incident={"schema":"agentos.persona-social-incident/v1","status":"open",
        "action_id":target.get("action_id"),"capability":target.get("capability"),
        "observed_at":now,"failure_class":"SOCIAL_ADAPTER_UNAVAILABLE","receipt_ref":ref,
        "repair_status":"pending","owner":"agentos.social_runtime"}
    # Source-owned identifier; never use caller/provider error text as a path.
    import hashlib
    key=hashlib.sha256(str(target.get("action_id")).encode()).hexdigest()[:20]
    save(root/"pdca/incidents"/(key+".json"),incident)
    save(root/"pdca/state.json",state)
    return receipt

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--persona-dir",required=True)
    ap.add_argument("--username",default="mio.milkcat")
    ap.add_argument("--receipt-out",required=True)
    args=ap.parse_args()
    root=Path(args.persona_dir)
    state=json.loads((root/"pdca/state.json").read_text(encoding="utf-8"))
    pending=list(state.get("pending_external_actions") or [])
    now_dt=datetime.now(timezone.utc)
    def due(x):
        nb=str(x.get("not_before") or "")
        if not nb: return True
        try: return datetime.fromisoformat(nb.replace("Z","+00:00")) <= now_dt
        except Exception: return False
    ready=[x for x in pending if isinstance(x,dict) and x.get("status")=="candidate" and due(x) and x.get("capability") in (
        "social.threads.observe","social.reply.review","social.reply.send","social.post.publish"
    )]
    # Due environmental reads precede existing write candidates; cognition still
    # decides whether any public reply or post is appropriate.
    target=next((x for x in ready if x.get("capability")=="social.threads.observe"),
                ready[0] if ready else None)
    now=now_dt.isoformat().replace("+00:00","Z")
    if not target:
        result={"schema":"agentos.persona-social-executor-receipt/v1","ok":True,"status":"NO_ACTION","timestamp":now}
        Path(args.receipt_out).parent.mkdir(parents=True,exist_ok=True)
        Path(args.receipt_out).write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        print(json.dumps(result,ensure_ascii=False)); return 0

    capability=target.get("capability")
    try:
        if capability in ("social.threads.observe","social.reply.review"):
            cfg=json.loads((root/"pdca/config.json").read_text(encoding="utf-8"))
            if cfg.get("enabled") is not True or state.get("status")!="RUNNING":
                raise RuntimeError("observation_not_authorized")
        env=parse_env(ENV)
        registry=json.loads(env["AGENTOS_SOCIAL_PRODUCTS_JSON"])
        product="galaxy"
        product_key=str(registry[product]["api_key"])
        creds=json.loads(CREDS.read_text(encoding="utf-8"))
        binding_id,binding=find_binding(creds,args.username)
        if not binding_id or not product_key:
            raise RuntimeError("persona_threads_binding_not_found")
        base={"schema":"agentos.social-request/v1","product_id":product,
              "platform":"threads","account_binding_id":binding_id}
        headers={"X-AgentOS-Product-Key":product_key}
        if capability in ("social.threads.observe","social.reply.review"):
            result=observe(root,state,target,Path(args.receipt_out),args.username,base,headers,now_dt)
            print(json.dumps(result,ensure_ascii=False)); return 0
    except (OSError,ValueError,TypeError,KeyError,RuntimeError):
        if capability in ("social.threads.observe","social.reply.review"):
            result=blocked_observation(root,state,target,Path(args.receipt_out),now)
            print(json.dumps(result,ensure_ascii=False)); return 0
        raise

    if capability in ("social.reply.send","social.post.publish"):
        text=str(target.get("primary_text") or "").strip()
        action_id=str(target.get("action_id") or "").strip()
        if not text or not action_id:
            raise SystemExit("social_write_intent_incomplete")
        request={
          **base,
          "operation":"reply" if capability=="social.reply.send" else "publish",
          "target_account_id":str(binding.get("provider_account_id") or ""),
          "primary_text":text,
          "write_intent_id":action_id,
        }
        if capability=="social.reply.send":
            reply_to=str(target.get("reply_to_id") or "").strip()
            if not reply_to: raise SystemExit("social_reply_target_required")
            request["reply_to_id"]=reply_to
        control=str(env.get("AGENTOS_SOCIAL_CONTROL_TOKEN") or "")
        if not control: raise SystemExit("social_control_token_missing")
        ac,accepted=post("/internal/v1/social/acceptances",request,{"X-AgentOS-Control-Token":control})
        acceptance_id=str(accepted.get("acceptance_id") or "")
        if ac not in (200,201) or not acceptance_id:
            raise SystemExit("social_acceptance_failed:"+str(accepted.get("error") or ac))
        endpoint="/v1/social/reply" if capability=="social.reply.send" else "/v1/social/publish"
        wc,wr=post(endpoint,request,{**headers,"X-AgentOS-Acceptance-ID":acceptance_id})
        if wc!=200 or wr.get("ok") is False:
            raise SystemExit("social_write_failed:"+str(wr.get("error") or wc))
        receipt={
          "schema":"agentos.persona-social-executor-receipt/v1","ok":True,"status":"EXECUTED",
          "timestamp":now,"persona_username":args.username,"capability":capability,
          "account_binding_id":binding_id,"action_id":action_id,
          "write_performed":True,"provider_receipt":wr
        }
        out=Path(args.receipt_out); out.parent.mkdir(parents=True,exist_ok=True)
        out.write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        events_path=root/"events/events.jsonl"
        result=wr.get("result") or {}
        object_id=str(result.get("id") or result.get("object_id") or "")
        with open(events_path,"a",encoding="utf-8") as fh:
            fh.write(json.dumps({
              "id":("threads:reply:" if capability=="social.reply.send" else "threads:post:")+(object_id or action_id),
              "type":"reply.sent" if capability=="social.reply.send" else "post.sent",
              "timestamp":now,"source":"agentos_shared_social_capability",
              "source_object_id":object_id or None,"actor":state.get("persona_id"),
              "text":text,"pdca_action_id":action_id,"pdca_external_receipt":str(out.relative_to(root))
            },ensure_ascii=False,separators=(",",":"))+"\n")
        for x in pending:
            if x is target:
                x["status"]="completed"; x["executed_at"]=now
                x["receipt_ref"]=str(out.relative_to(root)); x["provider_object_id"]=object_id or None
        state["pending_external_actions"]=pending[-12:]
        state["last_social_receipt"]=str(out.relative_to(root))
        tmp=root/"pdca/state.json.tmp"
        tmp.write_text(json.dumps(state,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        os.replace(tmp,root/"pdca/state.json")
        print(json.dumps(receipt,ensure_ascii=False)); return 0

    return 0

if __name__=="__main__":
    raise SystemExit(main())
