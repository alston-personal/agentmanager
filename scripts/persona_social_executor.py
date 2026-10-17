#!/usr/bin/env python3
import argparse, hashlib, json, os, re, urllib.request, urllib.error
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

def post(path,payload,headers,timeout=20):
    body=json.dumps(payload,ensure_ascii=False).encode()
    req=urllib.request.Request(RUNTIME+path,data=body,headers={"content-type":"application/json","accept":"application/json",**headers},method="POST")
    try:
        with urllib.request.urlopen(req,timeout=timeout) as r:
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


def save_private(path,value):
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    path.parent.chmod(0o700)
    tmp=path.with_suffix(path.suffix+".tmp")
    fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    with os.fdopen(fd,"w",encoding="utf-8") as fh:
        os.fchmod(fh.fileno(),0o600)
        fh.write(json.dumps(value,ensure_ascii=False,indent=2)+"\n")
    os.replace(tmp,path)


def timestamp(value):
    try:
        # Platform exports use +0000; Python 3.10 requires +00:00.
        text=str(value).strip().replace("Z","+00:00")
        text=re.sub(r"([+-]\d{2})(\d{2})$",r"\1:\2",text)
        dt=datetime.fromisoformat(text)
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
    activity_ref=str(state.get("last_activity_receipt") or "")
    if activity_ref:
        activity_path=root/activity_ref
        if activity_path.exists():
            activity=json.loads(activity_path.read_text(encoding="utf-8"))
            if activity.get("action_id")==action_id and activity.get("status")=="pending_external":
                activity["status"]="completed"
                activity["result"]=result
                activity["completed_at"]=observed_at
                activity["external_receipt_ref"]=ref
                activity["external_action_verified"]=True
                save(activity_path,activity)
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


def image_journal_path(action_id):
    directory=Path(os.environ.get("AGENTOS_PERSONA_WRITE_JOURNAL_DIR") or
                   "/home/ubuntu/agent-data/runtime/persona-social-writes")
    return directory/(hashlib.sha256(action_id.encode()).hexdigest()+".json")


def select_action(ready):
    """Keep reads first; let independent actions pass an unready image.

    A started image write must retain its reconciliation turn, including when
    a failed data push left a candidate in Git but a journal on the node.
    Selection never validates media or changes the deferred image intent.
    """
    # Observations are generally first, but an overdue reply must not be
    # starved by a fresh observation candidate on every social timer tick.
    # Use the existing write_intent_id/acceptance path for idempotency; do not
    # manufacture or refresh an intent here.
    now_utc=datetime.now(timezone.utc)
    overdue_replies=[]
    for action in ready:
        if action.get("capability")!="social.reply.send":
            continue
        try:
            eligible=datetime.fromisoformat(str(action.get("not_before") or "").replace("Z","+00:00"))
            if eligible.tzinfo is not None and now_utc-eligible >= timedelta(minutes=90):
                overdue_replies.append((eligible,action))
        except (ValueError,TypeError):
            continue
    if overdue_replies:
        return min(overdue_replies,key=lambda row:row[0])[1]

    observation=next((x for x in ready if x.get("capability")=="social.threads.observe"),None)
    if observation is not None:
        return observation

    def waiting_for_media(action):
        media=action.get("media_intent")
        key=action.get("action_id")
        return (action.get("status")=="candidate"
                and action.get("capability")=="social.post.publish"
                and isinstance(media,dict) and media.get("mode") in ("generate","existing_verified")
                and media.get("status")!="validated" and isinstance(key,str) and bool(key)
                and not image_journal_path(key).exists())

    return next((x for x in ready if not waiting_for_media(x)),ready[0] if ready else None)


def image_write(root,state,target,out,username,base,headers,control,now,energy_cost):
    """One IMAGE write, then read-only reconciliation across subsequent ticks.

    The local journal survives disposable data clones and failed Git pushes.
    Once dispatch starts, no retry is permitted to create a second container.
    """
    from persona_media_asset import resolve_asset,selection_digest
    action_id=target["action_id"]
    text=str(target["primary_text"]).strip()
    journal_path=image_journal_path(action_id)
    intent_digest=hashlib.sha256(json.dumps({"action_id":action_id,"text":text,
            "account":base["target_account_id"],"binding":base["account_binding_id"],
            "media_selection":selection_digest(target),
            "media_receipt":(target.get("media_intent") or {}).get("asset_receipt_ref")},
            sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    journal=json.loads(journal_path.read_text()) if journal_path.exists() else {}
    def finish(status,reason,*,ok=False,write_performed=False):
        receipt={"schema":"agentos.persona-social-executor-receipt/v1","ok":ok,
            "status":status,"result":reason,"timestamp":now,"action_id":action_id,
            "capability":"social.post.publish","write_performed":write_performed,
            "media_type":"IMAGE","platform_object_id":journal.get("platform_object_id"),
            "media_asset_receipt_ref":(target.get("media_intent") or {}).get("asset_receipt_ref")}
        if journal.get("provider_receipt"):
            receipt["provider_receipt"]=journal["provider_receipt"]
        save(out,receipt)
        target["receipt_ref"]=str(out.relative_to(root))
        target["media_blocked_reason"]=reason if not ok else None
        save(root/"pdca/state.json",state)
        return receipt
    if journal and journal.get("intent_sha256")!=intent_digest:
        target["status"]="blocked"
        return finish("BLOCKED","IMAGE_WRITE_INTENT_CHANGED")
    if not journal:
        if not control:
            return finish("BLOCKED","IMAGE_CONTROL_AUTHORITY_MISSING")
        try:
            persona=json.loads((root/"persona_state.json").read_text())
            cfg=json.loads((root/"pdca/config.json").read_text())
            if cfg.get("enabled") is not True or state.get("status")!="RUNNING" or (persona.get("autonomy") or {}).get("routine_posts")!="autonomous_with_policy":
                raise ValueError("MEDIA_POST_NOT_AUTHORIZED")
            asset=resolve_asset(root,target)
        except (OSError,ValueError,TypeError,KeyError):
            return finish("BLOCKED","MEDIA_NOT_VALIDATED_OR_AUTHORIZED")
        request={**base,"operation":"publish","primary_text":text,"write_intent_id":action_id,
            "image_url":asset["image_url"],"image_alt_text":asset["image_alt_text"]}
        ac,accepted=post("/internal/v1/social/acceptances",request,{"X-AgentOS-Control-Token":control})
        acceptance_id=str(accepted.get("acceptance_id") or "")
        if ac not in (200,201) or not acceptance_id:
            return finish("BLOCKED","IMAGE_ACCEPTANCE_FAILED")
        journal={"schema":"agentos.persona-image-write-journal/v1","intent_sha256":intent_digest,
                 "action_id":action_id,"phase":"dispatching","started_at":now,
                 "image_sha256":asset["image_sha256"]}
        save_private(journal_path,journal)
        target["status"]="in_progress"
        save(root/"pdca/state.json",state)
        try:
            wc,wr=post("/v1/social/publish",request,
                       {**headers,"X-AgentOS-Acceptance-ID":acceptance_id},timeout=100)
        except (OSError,ValueError,TypeError):
            target["status"]="blocked"
            return finish("WRITE_OUTCOME_UNKNOWN","IMAGE_WRITE_REQUIRES_RECONCILIATION",write_performed=None)
        object_id=str(wr.get("platform_object_id") or "")
        if wc!=200 or wr.get("ok") is not True or not object_id.isdigit() or wr.get("operation")!="publish" or wr.get("target_account_id")!=base["target_account_id"] or wr.get("account_binding_id")!=base["account_binding_id"]:
            target["status"]="blocked"
            return finish("WRITE_OUTCOME_UNKNOWN","IMAGE_PROVIDER_RECEIPT_UNCONFIRMED",write_performed=None)
        journal.update(phase="awaiting_readback",platform_object_id=object_id,provider_receipt=wr)
        save_private(journal_path,journal)
    object_id=str(journal.get("platform_object_id") or "")
    if not object_id.isdigit():
        target["status"]="blocked"
        return finish("WRITE_OUTCOME_UNKNOWN","IMAGE_WRITE_REQUIRES_RECONCILIATION",write_performed=None)
    # Debit once per durable action, including during an eventual readback hold.
    # If data push failed, the next clone still needs this same debit applied.
    if target.get("energy_debited") is not True:
        state["energy_current"]=round(float(state.get("energy_current",0))-energy_cost,2)
        target["energy_debited"]=True
    target.update(status="in_progress",provider_object_id=object_id)
    try:
        rows,adapter=read_items({**{k:v for k,v in base.items() if k!="target_account_id"},"operation":"post.read"},headers)
        row=next((x for x in rows if str(x.get("id") or "")==object_id),None)
        if not row or str(row.get("text") or "").strip()!=text or str(row.get("media_type") or "").upper()!="IMAGE" or row.get("image_visible") is not True or not str(row.get("permalink") or "").startswith("https://"):
            raise ValueError("IMAGE_READBACK_PENDING")
    except (OSError,ValueError,TypeError,KeyError,RuntimeError):
        return finish("AWAITING_READBACK","IMAGE_READBACK_PENDING",write_performed=True)
    target.update(status="completed",executed_at=journal["provider_receipt"].get("completed_at") or now,
                  media_readback_status="PASS")
    receipt=finish("EXECUTED","IMAGE_READBACK_PASS",ok=True,write_performed=True)
    receipt.update(permalink=row["permalink"],media_readback_status="PASS",readback_receipt=adapter,
                   image_sha256=journal["image_sha256"],energy_cost=energy_cost)
    save(out,receipt)
    state["last_social_receipt"]=str(out.relative_to(root))
    events_path=root/"events/events.jsonl"
    existing=[json.loads(line) for line in events_path.read_text().splitlines() if line.strip()]
    if not any(e.get("pdca_action_id")==action_id for e in existing):
        with events_path.open("a",encoding="utf-8") as fh:
            fh.write(json.dumps({"id":"threads:post:"+object_id,"type":"post.sent",
                "timestamp":target["executed_at"],"source":"agentos_shared_social_capability",
                "source_object_id":object_id,"actor":state.get("persona_id"),"text":text,
                "media_type":"IMAGE","permalink":row["permalink"],"parent_object_id":None,
                "pdca_action_id":action_id,"pdca_external_receipt":str(out.relative_to(root))},
                ensure_ascii=False,separators=(",",":"))+"\n")
    save(root/"pdca/state.json",state)
    journal["phase"]="completed"
    save_private(journal_path,journal)
    return receipt

def reconcile_held_reply(root, state, target, out, base, headers, now):
    """Read-only exact-parent recovery; absence never authorizes a resend."""
    parent=str(target.get("reply_to_id") or "")
    post_id=str(target.get("root_post_id") or "")
    text=str(target.get("primary_text") or "").strip()
    status="UNCONFIRMED"
    matched=[]
    if parent.isdigit() and post_id.isdigit() and text:
        try:
            items,_=read_items({**base,"operation":"replies.read","object_id":post_id},headers)
            matched=[str(row.get("id")) for row in items if isinstance(row,dict)
                     and str(row.get("id") or "").isdigit()
                     and row.get("is_reply_owned_by_me") is True
                     and str((row.get("replied_to") or {}).get("id") if isinstance(row.get("replied_to"),dict) else "")==parent
                     and str(row.get("text") or "").strip()==text]
            status="CONFIRMED" if len(matched)==1 else "AMBIGUOUS" if len(matched)>1 else "NOT_OBSERVED"
        except (OSError,ValueError,TypeError,RuntimeError):
            status="READ_FAILED"
    receipt={"schema":"agentos.persona-social-executor-receipt/v1",
             "timestamp":now,"capability":"social.reply.send",
             "action_id":target.get("action_id"),"operation":"reply.reconcile",
             "status":"RECONCILED" if status=="CONFIRMED" else "RECONCILIATION_PENDING",
             "readback_status":status,"write_performed":False,
             "delivery_confirmed":status=="CONFIRMED",
             "platform_object_id":matched[0] if status=="CONFIRMED" else None}
    save(out,receipt)
    target["reconciliation_receipt_ref"]=str(out.relative_to(root))
    if status=="CONFIRMED":
        target["status"]="completed"
        target["provider_object_id"]=matched[0]
        target["reconciliation_required"]=False
        target["receipt_ref"]=str(out.relative_to(root))
        intent=root/"pdca/reply_intents"/(str(target.get("action_id"))+".json")
        if intent.exists():
            original=json.loads(intent.read_text(encoding="utf-8"))
            original.update(status="completed",provider_object_id=matched[0],
                            receipt_ref=str(out.relative_to(root)),
                            reconciliation_required=False)
            save(intent,original)
    else:
        target["status"]="in_progress"
        target["reconciliation_required"]=True
        target["next_reconcile_not_before"]=(datetime.fromisoformat(now.replace("Z","+00:00"))+timedelta(minutes=30)).isoformat().replace("+00:00","Z")
        # Persist the uncertainty in the durable intent ledger as well.
        # A stale 'candidate' record must not authorize a second send.
        intent=root/"pdca/reply_intents"/(str(target.get("action_id"))+".json")
        if intent.exists():
            try:
                original=json.loads(intent.read_text(encoding="utf-8"))
                if (original.get("action_id")==target.get("action_id") and
                    original.get("capability")=="social.reply.send"):
                    original.update(status="in_progress",reconciliation_required=True,
                                    write_replay_allowed=False,
                                    reconciliation_receipt_ref=str(out.relative_to(root)))
                    save(intent,original)
            except (OSError,ValueError,TypeError):
                pass
    save(root/"pdca/state.json",state)
    return receipt

def recover_orphan_reply_intent(root, state):
    """Restore one lost reply for READ-ONLY reconciliation, never for sending.

    reply_intents/ is durable across the bounded pending queue; do not
    interpret absence from pending as permission to publish again.
    """
    pending=state.get("pending_external_actions") or []
    tracked={str(x.get("action_id")) for x in pending if isinstance(x,dict)}
    historical=[]
    for path in (root/"pdca/reply_intents").glob("*.json"):
        try:
            record=json.loads(path.read_text(encoding="utf-8"))
        except (OSError,ValueError,TypeError):
            continue
        if not isinstance(record,dict) or record.get("capability")!="social.reply.send":
            continue
        aid=str(record.get("action_id") or "")
        if not aid or aid in tracked or record.get("status") in ("completed","cancelled","superseded","skipped"):
            continue
        if not str(record.get("reply_to_id") or "").isdigit() or not str(record.get("root_post_id") or "").isdigit():
            continue
        historical.append((str(record.get("created_at") or ""),path,record))
    if not historical:
        return None
    _,path,record=min(historical,key=lambda x:(x[0],str(x[1])))
    restored={**record,"status":"in_progress","reconciliation_required":True,
              "recovery_source":"durable_reply_intent","write_replay_allowed":False}
    # Keep the complete pending ledger; do not evict another live task.
    pending.append(restored)
    state["pending_external_actions"]=pending
    save(root/"pdca/state.json",state)
    return restored


def select_reconciliation_fair_action(held, ready, cycle):
    """Never starve eligible reads or replay held writes; keep readback turns."""
    due_reads=[x for x in ready if x.get("capability") in
               ("social.threads.observe","social.reply.review")]
    if held is not None and due_reads and cycle % 2 == 1:
        return select_action(due_reads)
    return held or select_action(ready)


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--persona-dir",required=True)
    ap.add_argument("--username",default="mio.milkcat")
    ap.add_argument("--receipt-out",required=True)
    args=ap.parse_args()
    root=Path(args.persona_dir)
    state=json.loads((root/"pdca/state.json").read_text(encoding="utf-8"))
    orphan=recover_orphan_reply_intent(root,state)
    pending=list(state.get("pending_external_actions") or [])
    now_dt=datetime.now(timezone.utc)
    def due(x):
        nb=str(x.get("not_before") or "")
        if not nb: return True
        try: return datetime.fromisoformat(nb.replace("Z","+00:00")) <= now_dt
        except Exception: return False
    held=next((x for x in pending if isinstance(x,dict)
        and x.get("capability")=="social.reply.send" and x.get("status")=="in_progress"
        and x.get("reconciliation_required") is True
        and (not x.get("next_reconcile_not_before") or
             timestamp(x["next_reconcile_not_before"]) is not None and
             timestamp(x["next_reconcile_not_before"]) <= now_dt)),None)
    ready=[x for x in pending if isinstance(x,dict) and (x.get("status")=="candidate" or
        (x.get("status")=="in_progress" and x.get("capability")=="social.post.publish" and
         (x.get("media_intent") or {}).get("mode") in ("generate","existing_verified"))) and due(x) and x.get("capability") in (
        "social.threads.observe","social.reply.review","social.reply.send","social.post.publish"
    )]
    # A held reply may require repeated READ-ONLY reconciliation for days.
    # Alternate with independently due observation/review so it cannot starve
    # Mio's external awareness. Never replay a held write.
    target=select_reconciliation_fair_action(
        held, ready, int(state.get("cycle") or 0))
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
        if held is target:
            result=reconcile_held_reply(root,state,target,Path(args.receipt_out),base,headers,now_dt.isoformat().replace("+00:00","Z"))
            print(json.dumps(result,ensure_ascii=False)); return 0
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

        # Media is a separate, receipt-gated capability. Never silently send
        # text-only when Mio explicitly chose an image that is not ready.
        media=target.get("media_intent") or {}
        if not isinstance(media,dict) or (media and media.get("mode") not in ("none","generate","existing_verified")):
            receipt={"schema":"agentos.persona-social-executor-receipt/v1","ok":False,
                "status":"BLOCKED","result":"MEDIA_INTENT_INVALID","action_id":action_id,
                "timestamp":now,"write_performed":False}
            save(Path(args.receipt_out),receipt)
            print(json.dumps(receipt)); return 0
        if capability=="social.post.publish" and media.get("mode") in ("generate","existing_verified"):
            cost=float((json.loads((root/"persona_state.json").read_text()).get("energy") or {}).get("action_costs",{}).get("new_post",8))
            # Reconciliation is read-only and remains possible at zero energy.
            if float(state.get("energy_current",0))<=0 and target.get("status")!="in_progress":
                if not image_journal_path(action_id).exists():
                    receipt={"ok":False,"status":"BLOCKED","result":"ENERGY_DEPLETED","write_performed":False}
                    save(Path(args.receipt_out),receipt)
                    print(json.dumps(receipt)); return 0
            result=image_write(root,state,target,Path(args.receipt_out),args.username,
                {**base,"target_account_id":str(binding.get("provider_account_id") or "")},headers,
                str(env.get("AGENTOS_SOCIAL_CONTROL_TOKEN") or ""),now,cost)
            print(json.dumps(result,ensure_ascii=False)); return 0

        persona=json.loads((root/"persona_state.json").read_text(encoding="utf-8"))
        energy_cfg=persona.get("energy",{}) if isinstance(persona.get("energy"),dict) else {}
        action_costs=energy_cfg.get("action_costs",{}) if isinstance(energy_cfg.get("action_costs"),dict) else {}
        energy=float(state.get("energy_current",energy_cfg.get("current",0)))
        if capability=="social.post.publish":
            energy_cost=float(action_costs.get("new_post",8))
        else:
            energy_cost=float(action_costs.get("short_reply",3) if len(text)<=160
                              else action_costs.get("long_reply",5))
        if energy <= 0:
            retry_at=(now_dt+timedelta(minutes=30)).isoformat().replace("+00:00","Z")
            target["not_before"]=retry_at
            receipt={
              "schema":"agentos.persona-social-executor-receipt/v1","ok":False,
              "status":"BLOCKED","result":"ENERGY_DEPLETED","timestamp":now,
              "persona_username":args.username,"capability":capability,
              "action_id":action_id,"write_performed":False,
              "energy_before":round(energy,2),"energy_cost":energy_cost,
              "energy_after":round(energy,2),"retry_not_before":retry_at
            }
            out=Path(args.receipt_out); out.parent.mkdir(parents=True,exist_ok=True)
            out.write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
            state["pending_external_actions"]=pending[-12:]
            save(root/"pdca/state.json",state)
            print(json.dumps(receipt,ensure_ascii=False)); return 0
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
        def hold_reply(reason):
            # Unknown acceptance/write outcomes must never be retried blindly.
            receipt={"schema":"agentos.persona-social-executor-receipt/v1",
                     "ok":False,"status":"BLOCKED","result":reason,
                     "timestamp":now,"action_id":action_id,"capability":capability,
                     "write_performed":False,"delivery_confirmed":False,
                     "requires_platform_reconciliation":True}
            out=Path(args.receipt_out)
            save(out,receipt)
            target["status"]="in_progress"
            target["reconciliation_required"]=True
            target["receipt_ref"]=str(out.relative_to(root))
            # Preserve the held action even when the bounded queue is full.
            # Truncating here could lose the very reconciliation obligation.
            state["pending_external_actions"]=pending
            save(root/"pdca/state.json",state)
            print(json.dumps(receipt,ensure_ascii=False))
            return 0
        if not control:
            if capability=="social.reply.send":
                return hold_reply("SOCIAL_CONTROL_UNAVAILABLE")
            raise SystemExit("social_control_token_missing")
        try:
            ac,accepted=post("/internal/v1/social/acceptances",request,{"X-AgentOS-Control-Token":control})
        except (OSError,ValueError,TimeoutError):
            if capability=="social.reply.send":
                return hold_reply("SOCIAL_ACCEPTANCE_UNKNOWN")
            raise
        acceptance_id=str(accepted.get("acceptance_id") or "")
        if ac not in (200,201) or not acceptance_id:
            if capability=="social.reply.send":
                return hold_reply("SOCIAL_ACCEPTANCE_NOT_CONFIRMED")
            raise SystemExit("social_acceptance_failed:"+str(accepted.get("error") or ac))
        endpoint="/v1/social/reply" if capability=="social.reply.send" else "/v1/social/publish"
        try:
            wc,wr=post(endpoint,request,{**headers,"X-AgentOS-Acceptance-ID":acceptance_id})
        except (OSError,ValueError,TimeoutError):
            if capability=="social.reply.send":
                return hold_reply("SOCIAL_DELIVERY_UNKNOWN")
            raise
        if wc!=200 or wr.get("ok") is False:
            if capability=="social.reply.send":
                return hold_reply("SOCIAL_DELIVERY_NOT_CONFIRMED")
            raise SystemExit("social_write_failed:"+str(wr.get("error") or wc))
        energy_after=energy-energy_cost
        state["energy_current"]=round(energy_after,2)
        receipt={
          "schema":"agentos.persona-social-executor-receipt/v1","ok":True,"status":"EXECUTED",
          "timestamp":now,"persona_username":args.username,"capability":capability,
          "account_binding_id":binding_id,"action_id":action_id,
          "write_performed":True,"provider_receipt":wr,
          "energy_before":round(energy,2),"energy_cost":energy_cost,
          "energy_after":round(energy_after,2)
        }
        out=Path(args.receipt_out); out.parent.mkdir(parents=True,exist_ok=True)
        out.write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        events_path=root/"events/events.jsonl"
        result=wr.get("result") or {}
        object_id=str(wr.get("platform_object_id") or result.get("id") or result.get("object_id") or "")
        with open(events_path,"a",encoding="utf-8") as fh:
            fh.write(json.dumps({
              "id":("threads:reply:" if capability=="social.reply.send" else "threads:post:")+(object_id or action_id),
              "type":"reply.sent" if capability=="social.reply.send" else "post.sent",
              "timestamp":now,"source":"agentos_shared_social_capability",
              "source_object_id":object_id or None,"actor":state.get("persona_id"),
              "parent_object_id":target.get("reply_to_id") if capability=="social.reply.send" else None,
              "root_post_id":target.get("root_post_id") if capability=="social.reply.send" else object_id or None,
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
