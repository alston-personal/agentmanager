#!/usr/bin/env python3
import argparse, hashlib, json, random, re
from datetime import datetime, timedelta, timezone
from pathlib import Path
import persona_post_intent_generator as reasoning
from persona_social_executor import save, timestamp

def load(p):
    with open(p,"r",encoding="utf-8") as f: return json.load(f)

def read_events(path):
    out=[]
    if not path.exists(): return out
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            v=json.loads(line)
            if isinstance(v,dict): out.append(v)
        except Exception: pass
    return out

def normalize_ts(v):
    return timestamp(v)

def terminal_action(action):
    return isinstance(action,dict) and action.get("status") in {"completed","cancelled","superseded","skipped"}

def already_replied(events, reply):
    rid=str(reply.get("object_id") or reply.get("source_object_id") or "")
    for e in events:
        if e.get("type")!="reply.sent": continue
        parent=str(e.get("parent_object_id") or e.get("reply_to_id") or "")
        if rid and parent==rid: return True
    return False

def reserved_reply_parents(root, pending):
    """Persistent reservation: dropped queue entries are not permission to reply twice.

    All previous reply intents remain reserved until platform reconciliation
    proves that it is safe to close them. A conservative hold beats duplicate
    public replies when a data clone or state truncation loses a candidate.
    """
    parents={str(action.get("reply_to_id")) for action in pending
             if isinstance(action,dict) and action.get("capability")=="social.reply.send"
             and action.get("reply_to_id")}
    for path in (root/"pdca/reply_intents").glob("*.json"):
        try:
            old=load(path)
            if old.get("capability")=="social.reply.send" and old.get("reply_to_id"):
                parents.add(str(old["reply_to_id"]))
        except (OSError,ValueError,TypeError):
            continue
    return parents


def reply_candidates(events,state,ir_binding,reserved_parents=None):
    """Routeable comments only; a historical screenshot cannot starve the queue."""
    skipped={}
    candidates={}
    decisions=state.get("reply_decisions") or {}
    reserved_parents=reserved_parents or set()
    for event in events:
        if event.get("type")!="reply.observed": continue
        author=str(event.get("author_handle") or event.get("username") or "").lstrip("@").casefold()
        if str(event.get("actor") or "")==str(state.get("persona_id")) or author=="mio.milkcat": continue
        if event.get("is_reply_owned_by_me") is True or already_replied(events,event): continue
        text=str(event.get("text") or event.get("summary") or "").strip()
        if not text: continue
        rid=str(event.get("object_id") or event.get("source_object_id") or "")
        if rid in reserved_parents:
            skipped["already_reserved"]=skipped.get("already_reserved",0)+1
            continue
        root_id=str(event.get("root_post_id") or event.get("root_id") or "")
        root_post=root_text(events,root_id)
        stamp=normalize_ts(event.get("timestamp"))
        reason=("missing_route_ids" if not rid.isdigit() or not root_id.isdigit() else
                "missing_root_post" if not root_post else "invalid_timestamp" if stamp is None else None)
        if reason:
            skipped[reason]=skipped.get(reason,0)+1
            continue
        key=hashlib.sha256(json.dumps({"reply_id":rid,"root_id":root_id,"text":text,
            "root_post":root_post,"ir_source_sha256":ir_binding["source_sha256"]},
            ensure_ascii=False,sort_keys=True).encode()).hexdigest()
        previous=decisions.get(rid,{})
        if previous.get("context_sha256")==key and previous.get("status") in ("NO_REPLY","HUMAN_REQUIRED"):
            skipped["already_reviewed"]=skipped.get("already_reviewed",0)+1
            continue
        candidates[rid]={"event":event,"reply_id":rid,"root_id":root_id,"root_post":root_post,
                         "timestamp":stamp,"context_sha256":key}
    return sorted(candidates.values(),key=lambda x:x["timestamp"],reverse=True),skipped

def _verified_parent_rows(receipt):
    """An exact, independently attested parent ID; never decode URL shortcodes."""
    result = receipt.get("result")
    if not isinstance(result, dict):
        return None
    if receipt.get("operation") == "keyword.search":
        items = result.get("items")
        return items if isinstance(items, list) and len(items) <= 10 else None
    if (receipt.get("operation") == "parent_identity.read"
            and receipt.get("capability") == "social.threads.parent_identity.read"):
        identity = result.get("identity")
        if (isinstance(identity, dict)
                and identity.get("provider_verified") is True
                and identity.get("numeric_id_source") == "provider"
                and identity.get("is_reply_attested") is True
                and identity.get("is_reply") is False
                and str(identity.get("root_post_id") or "") == str(identity.get("id") or "")
                and str(identity.get("id") or "").isdigit()):
            return [identity]
    return None


def project_external_verified_events(root, policy, now, limit=80):
    """Reuse persisted Core Reader + independently attested identity; no network/writes.

    Only an independently attested non-reply from a trusted provider
    can supply the numeric parent. The HTML read supplies bounded context.
    The derived event is in-memory; both original receipts remain authoritative.
    """
    if policy.get("proactive_external_reply_authorized") is not True:
        return []
    folder = root / "pdca/social_receipts"
    if not folder.is_dir():
        return []
    candidates = sorted(folder.glob("*.json"), reverse=True)[:limit]
    html, searches = [], []
    for path in candidates:
        try:
            if path.is_symlink() or path.stat().st_size > 100_000:
                continue
            raw = load(path)
            receipt = raw.get("provider_receipt") if isinstance(raw, dict) else None
            if not isinstance(receipt, dict):
                receipt = raw
            if not isinstance(receipt, dict) or receipt.get("ok") is not True:
                continue
            stamp = normalize_ts(receipt.get("completed_at"))
            if stamp is None or not timedelta(0) <= now - stamp <= timedelta(hours=72):
                continue
            ref = "pdca/social_receipts/" + path.name
            if receipt.get("schema") != "agentos.social-receipt/v1":
                continue
            if not receipt.get("account_binding_id") or receipt.get("platform") != "threads":
                continue
            result = receipt.get("result")
            if not isinstance(result, dict):
                continue
            if receipt.get("operation") == "public_post.read":
                source = result.get("source")
                if isinstance(source, dict) and source.get("url") and source.get("text"):
                    html.append((ref, receipt, source))
            elif receipt.get("operation") in ("keyword.search", "parent_identity.read"):
                rows = _verified_parent_rows(receipt)
                if rows is not None:
                    searches.append((ref, receipt, rows))
        except (OSError, ValueError, TypeError):
            continue
    output = []
    seen = set()
    for source_ref, public, source in html[:20]:
        url = str(source.get("url") or "")
        username = str(source.get("username") or "").casefold()
        text = str(source.get("text") or "").strip()
        if (not username or username == "mio.milkcat"
                or not url.startswith("https://www.threads.com/") or not text):
            continue
        for search_ref, search, rows in searches[:20]:
            if search.get("account_binding_id") != public.get("account_binding_id"):
                continue
            if abs((normalize_ts(search["completed_at"]) -
                    normalize_ts(public["completed_at"])).total_seconds()) > 300:
                continue
            matches = [item for item in rows if isinstance(item, dict)
                       and str(item.get("id") or "").isdigit()
                       and item.get("is_reply_attested") is True
                       and item.get("is_reply") is False
                       and str(item.get("username") or "").casefold() == username
                       and str(item.get("permalink") or "") == url
                       and str(item.get("text") or "").strip() == text
                       and (search.get("operation") == "keyword.search" or
                            (item.get("provider_verified") is True and
                             item.get("numeric_id_source") == "provider" and
                             str(item.get("root_post_id") or "") == str(item.get("id") or "")))]
            if len(matches) != 1:
                continue
            parent = str(matches[0]["id"])
            if parent in seen:
                continue
            seen.add(parent)
            output.append({
                "type": "public.post.verified", "object_id": parent,
                "root_post_id": parent, "reader_account": "mio.milkcat",
                "author_handle": username, "text": text,
                "source_url": url, "source_receipt_ref": source_ref,
                "search_receipt_ref": search_ref,
                "account_binding_id": search["account_binding_id"],
                "timestamp": search["completed_at"]
            })
            break
        if len(output) >= 5:
            break
    return output


def external_reply_candidates(root, events, state, ir_binding, policy, reserved_parents, now):
    """Accept outward roots only with an independent platform read and write policy.

    Historical read-only Inbox entries are deliberately NOT an input here.
    An event or a numeric ID alone never grants reply authority.
    """
    if not any(event.get("type") == "public.post.verified" for event in events):
        return [], {}
    if policy.get("proactive_external_reply_authorized") is not True:
        return [], {"external_reply_not_authorized": 1}
    candidates, skipped = [], {}
    for event in events:
        if event.get("type") != "public.post.verified":
            continue
        parent = str(event.get("object_id") or "")
        root_id = str(event.get("root_post_id") or "")
        receipt_ref = event.get("source_receipt_ref")
        author = str(event.get("author_handle") or "").lstrip("@").casefold()
        def reject(reason):
            skipped[reason] = skipped.get(reason, 0) + 1
        if (not parent.isdigit() or not root_id.isdigit() or parent != root_id
                or not author or author == "mio.milkcat" or parent in reserved_parents):
            reject("external_parent_unrouteable")
            continue
        if not isinstance(receipt_ref, str) or not re.fullmatch(
                r"pdca/social_receipts/[A-Za-z0-9_-]{1,100}\.json", receipt_ref):
            reject("external_source_receipt_missing")
            continue
        try:
            source = load(root / receipt_ref)
        except (OSError, ValueError, TypeError):
            reject("external_source_receipt_missing")
            continue
        provider = source.get("provider_receipt") if isinstance(source, dict) else None
        if not isinstance(provider, dict):
            provider = source if isinstance(source, dict) else {}
        source_content = (provider.get("result") or {}).get("source") if isinstance(provider.get("result"), dict) else None
        # The canonical HTML Reader proves content, not Meta's numeric object ID.
        # Independently corroborate ID/permalink through an account-bound
        # official keyword.search receipt; never derive an ID from a shortcode.
        search_ref = event.get("search_receipt_ref")
        if not isinstance(search_ref, str) or not re.fullmatch(
                r"pdca/social_receipts/[A-Za-z0-9_-]{1,100}\.json", search_ref):
            reject("external_search_receipt_missing")
            continue
        try:
            search = load(root / search_ref)
        except (OSError, ValueError, TypeError):
            reject("external_search_receipt_missing")
            continue
        search_provider = search.get("provider_receipt") if isinstance(search, dict) else None
        if not isinstance(search_provider, dict):
            search_provider = search if isinstance(search, dict) else {}
        search_items = _verified_parent_rows(search_provider)
        if (not isinstance(search_items, list) or len(search_items) > 10
                or search_provider.get("schema") != "agentos.social-receipt/v1"
                or search_provider.get("ok") is not True
                or search_provider.get("operation") not in ("keyword.search", "parent_identity.read")
                or search_provider.get("account_binding_id") != event.get("account_binding_id")
                or provider.get("schema") != "agentos.social-receipt/v1"
                or provider.get("ok") is not True
                or provider.get("operation") != "public_post.read"
                or (provider.get("platform_object_id") is not None
                    and str(provider["platform_object_id"]) != parent)
                or not isinstance(source_content, dict)
                or str(source_content.get("username") or "").casefold() != author
                or not provider.get("account_binding_id")
                or provider.get("account_binding_id") != event.get("account_binding_id")
                or str(source_content.get("url") or "") != str(event.get("source_url") or "")
                or str(event.get("reader_account") or "").casefold() != "mio.milkcat"):
            reject("external_source_unverified")
            continue
        matches = [row for row in search_items if isinstance(row, dict)
                   and str(row.get("id") or "") == parent
                   and str(row.get("permalink") or "") == event.get("source_url")
                   and str(row.get("username") or "").casefold() == author
                   and str(row.get("text") or "").strip() == str(source_content.get("text") or "").strip()]
        if len(matches) != 1:
            reject("external_numeric_id_unverified")
            continue
        # Root verification is separate: omitted reply/root fields must never
        # be treated as an explicit non-reply declaration.
        match = matches[0]
        if match.get("is_reply_attested") is not True or match.get("is_reply") is not False:
            reject("external_root_unverified")
            continue
        if (search_provider.get("operation") == "parent_identity.read" and
                (match.get("provider_verified") is not True or
                 match.get("numeric_id_source") != "provider" or
                 str(match.get("root_post_id") or "") != parent)):
            reject("external_root_unverified")
            continue
        read_at = normalize_ts(provider.get("completed_at"))
        search_at = normalize_ts(search_provider.get("completed_at"))
        observed_at = normalize_ts(event.get("timestamp"))
        if (read_at is None or search_at is None or observed_at is None
                or not timedelta(0) <= now - read_at <= timedelta(hours=72)
                or not timedelta(0) <= now - search_at <= timedelta(hours=72)
                or abs((observed_at - read_at).total_seconds()) > 300
                or abs((observed_at - search_at).total_seconds()) > 300):
            reject("external_read_receipt_stale")
            continue
        body = str(source_content.get("text") or "").strip()
        if not body or body != str(event.get("text") or "").strip():
            reject("external_context_mismatch")
            continue
        stamp = normalize_ts(event.get("timestamp"))
        if stamp is None or not timedelta(0) <= now - stamp <= timedelta(hours=72):
            reject("external_observation_stale")
            continue
        if already_replied(events, {"object_id": parent}):
            reject("external_already_replied")
            continue
        key = hashlib.sha256(json.dumps({
            "reply_id": parent, "root_id": root_id, "text": body,
            "source_receipt_ref": receipt_ref, "search_receipt_ref": search_ref,
            "ir_source_sha256": ir_binding["source_sha256"]
        }, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        prior = (state.get("reply_decisions") or {}).get(parent, {})
        if prior.get("context_sha256") == key and prior.get("status") in ("NO_REPLY", "HUMAN_REQUIRED"):
            reject("external_already_reviewed")
            continue
        candidates.append({
            "event": event, "reply_id": parent, "root_id": root_id,
            "root_post": body, "timestamp": stamp, "context_sha256": key,
            "external_root": True, "source_receipt_ref": receipt_ref,
            "search_receipt_ref": search_ref
        })
    return sorted(candidates, key=lambda c: c["timestamp"], reverse=True), skipped

def persist_reply_receipt(root,state,status,reason,now,**evidence):
    report={"schema":"agentos.persona-reply-reasoning-receipt/v1","cycle":state.get("cycle"),
        "status":status,"reason":reason,"generator_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "reasoning_runtime_sha256":hashlib.sha256(Path(reasoning.__file__).read_bytes()).hexdigest(),
        "diagnostic_contract":"sanitized-failure-class/v1",
        "reasoning_availability":reasoning.reasoning_availability(evidence.get("attempts") or []),
        "publication_acceptance":"NOT_OBSERVED",**evidence}
    # Unchanged non-provider defers do not create a receipt every five minutes.
    old_ref=state.get("last_reply_reasoning_receipt")
    if old_ref and not report.get("attempts"):
        try:
            old=load(root/old_ref)
            if {k:v for k,v in old.items() if k!="timestamp"}==report: return old_ref
        except (OSError,ValueError): pass
    ref=f"pdca/reply_reasoning/{now.strftime('%Y-%m-%d')}/{now.strftime('%H%M%S%f')}.json"
    save(root/ref,{**report,"timestamp":now.isoformat().replace("+00:00","Z")})
    state["last_reply_reasoning_receipt"]=ref
    save(root/"pdca/state.json",state)
    return ref

def extract_decision(text):
    decision=reasoning.extract_json(text)
    if not isinstance(decision,dict) or decision.get("position") not in {
        "agree","partly_agree","disagree","uncertain","playful_only","no_reply"}:
        raise ValueError("invalid_position")
    if type(decision.get("should_reply")) is not bool or type(decision.get("human_required")) is not bool:
        raise ValueError("invalid_reply_decision")
    if not isinstance(decision.get("reply_text"),str) or not isinstance(decision.get("reason"),str):
        raise ValueError("invalid_reply_decision")
    return decision

def root_text(events,root_id):
    for e in reversed(events):
        oid=str(e.get("object_id") or e.get("source_object_id") or "")
        if oid==root_id and e.get("type") in ("post.sent","post.published"):
            return str(e.get("text") or e.get("summary") or "").strip()
    return ""

def prior_thread(events,root_id,limit=8):
    rows=[]
    for e in events:
        if str(e.get("root_post_id") or e.get("root_id") or "")!=root_id: continue
        if e.get("type") not in ("reply.observed","reply.sent"): continue
        rows.append({
          "type":e.get("type"),"author":e.get("author_handle") or e.get("username"),
          "text":str(e.get("text") or e.get("summary") or "")[:500],
          "timestamp":e.get("timestamp")
        })
    return rows[-limit:]

def relationship_context(events,handle,limit=8):
    rows=[]
    for e in events:
        h=str(e.get("author_handle") or e.get("username") or "")
        if h.lower()!=handle.lower(): continue
        if e.get("type") not in ("reply.observed","reply.sent"): continue
        rows.append({"type":e.get("type"),"text":str(e.get("text") or e.get("summary") or "")[:400],"timestamp":e.get("timestamp")})
    return rows[-limit:]

def safe_reply_text(text):
    if not isinstance(text,str): return False
    s=text.strip()
    if not s or len(s)>320: return False
    if "http://" in s or "https://" in s: return False
    if len(re.findall(r'[😀-🙏🌀-🫿]',s))>2: return False
    return True

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--persona-dir",required=True)
    args=ap.parse_args()
    root=Path(args.persona_dir)
    state=load(root/"pdca/state.json")
    now=datetime.now(timezone.utc)
    try:
        ir,ir_context,ir_binding=reasoning.read_ir_authoring_context(root/"ir/current.json")
    except (OSError,ValueError,TypeError):
        persist_reply_receipt(root,state,"DEFER","current_ir_unavailable",now)
        print(json.dumps({"status":"DEFER","reason":"current_ir_unavailable"})); return 0
    policy=load(root/"reply_policy.json")
    stances=load(root/"social_stances.json")
    persona=load(root/"persona_state.json")
    events=read_events(root/"events/events.jsonl")
    # Derive bounded event candidates only from two separately persisted,
    # mutually agreeing read receipts. Do not mutate the event journal.
    events.extend(project_external_verified_events(root,policy,now))
    pending=list(state.get("pending_external_actions") or [])
    if any(x.get("status") in ("candidate","in_progress") and x.get("capability")=="social.reply.send" for x in pending if isinstance(x,dict)):
        print(json.dumps({"status":"SKIP","reason":"reply_send_already_pending"},ensure_ascii=False)); return 0
    reserved=reserved_reply_parents(root,pending)
    observed,skipped=reply_candidates(events,state,ir_binding,reserved)
    if not observed:
        outward,outward_skipped=external_reply_candidates(root,events,state,ir_binding,policy,reserved,now)
        observed=outward
        skipped.update(outward_skipped)
    if not observed:
        status="DEFER" if any(k!="already_reviewed" for k in skipped) else "NO_CANDIDATE"
        reason="no_routeable_comment" if status=="DEFER" else "no_unreviewed_comment"
        persist_reply_receipt(root,state,status,reason,now,selection_skipped=skipped,ir_authoring_context=ir_binding)
        print(json.dumps({"status":status,"reason":reason},ensure_ascii=False)); return 0
    if sum(not terminal_action(x) for x in pending)>=12:
        persist_reply_receipt(root,state,"DEFER","pending_capacity",now,selection_skipped=skipped)
        print(json.dumps({"status":"DEFER","reason":"pending_capacity"})); return 0

    selected=observed[0]
    candidate=selected["event"]
    reply_id=selected["reply_id"]
    root_id=selected["root_id"]
    handle=str(candidate.get("author_handle") or candidate.get("username") or "unknown")
    text=str(candidate.get("text") or candidate.get("summary") or "").strip()
    root_post=selected["root_post"]
    thread=prior_thread(events,root_id)
    relationship=relationship_context(events,handle)

    contract={
      "current_ir":ir_context,
      "reply_policy":policy,
      "social_stances":stances,
      "voice":persona.get("voice"),
      "autonomy":persona.get("autonomy"),
      "thread":({"root_post":{"id":root_id,"author":handle,"text":root_post},
                 "external_post":{"id":reply_id,"author":handle,"text":text},
                 "recent_thread":thread} if selected.get("external_root") else
                {"root_post":root_post,"incoming_reply":{"id":reply_id,"author":handle,"text":text},
                 "recent_thread":thread}),
      "relationship_context":relationship,
      "conversation_kind":"external_public_root" if selected.get("external_root") else "owned_post_incoming_reply",
      "source_receipt_ref":selected.get("source_receipt_ref"),
      "search_receipt_ref":selected.get("search_receipt_ref")
    }
    prompt="""You are deciding whether Mio should participate in a public Threads conversation.
The JSON context below is authoritative. Do not invent biography, facts, purchases, locations, or relationship history.
First decide Mio's private position: agree, partly_agree, disagree, uncertain, playful_only, or no_reply.
Only propose a public reply when context is sufficient and replying is useful. For an external_public_root, reply to the external author's original discussion rather than treating it as a reply to Mio. Hostile bait may be no_reply. Legal/payment/contracts/private data must be no_reply and human_required=true.
Keep the public reply short, natural Traditional Chinese, consistent with Mio's current IR. Do not mention internal systems/policies. Do not overuse emoji (0-2 max).
Return ONLY one JSON object with exactly these keys:
{"position":"...","should_reply":true|false,"human_required":true|false,"reason":"short internal reason","reply_text":"public text or empty"}
Context:
"""+json.dumps(contract,ensure_ascii=False)

    decision,executor,attempts=reasoning.reason_with_providers(prompt,extract_decision,
        reasoning.discover_executor(),reasoning.discover_gemini_executor(),reasoning.discover_codex_executor())
    evidence={"reply_id":reply_id,"root_post_id":root_id,"context_sha256":selected["context_sha256"],
              "selection_skipped":skipped,"attempts":attempts,"ir_authoring_context":ir_binding}
    if decision is None:
        persist_reply_receipt(root,state,"DEFER","persona_reasoning_exhausted",datetime.now(timezone.utc),**evidence)
        print(json.dumps({"status":"DEFER","reason":"persona_reasoning_exhausted"})); return 0
    try:
        unchanged=hashlib.sha256((root/"ir/current.json").read_bytes()).hexdigest()==ir_binding["source_sha256"]
    except OSError: unchanged=False
    if not unchanged:
        persist_reply_receipt(root,state,"DEFER","current_ir_changed",datetime.now(timezone.utc),**evidence)
        print(json.dumps({"status":"DEFER","reason":"current_ir_changed"})); return 0

    position=decision["position"]
    should=decision["should_reply"]
    human=decision["human_required"]
    reply_text=str(decision.get("reply_text") or "").strip()
    if human or position=="no_reply" or not should:
        status="HUMAN_REQUIRED" if human else "NO_REPLY"
        decisions=dict(state.get("reply_decisions") or {})
        decisions[reply_id]={"status":status,"context_sha256":selected["context_sha256"],
            "position":position,"reason":decision["reason"][:300]}
        state["reply_decisions"]=dict(list(decisions.items())[-2000:])
        persist_reply_receipt(root,state,status,"review_completed_without_send",datetime.now(timezone.utc),
                              position=position,**evidence)
        print(json.dumps({"status":status,"position":position,"human_required":human},ensure_ascii=False)); return 0
    if not safe_reply_text(reply_text):
        persist_reply_receipt(root,state,"DEFER","reply_text_guard_failed",datetime.now(timezone.utc),**evidence)
        print(json.dumps({"status":"DEFER","reason":"reply_text_guard_failed"},ensure_ascii=False)); return 0

    # Respect Mio's configured reply latency instead of replying instantly by default.
    latency=persona.get("temporal_behavior",{}).get("reply_latency",{}).get("typical_minutes",[8,45])
    lo,hi=int(latency[0]),int(latency[-1])
    seed=int(hashlib.sha256(f"{reply_id}|{state.get('cycle')}|{ir.get('ir_id')}".encode()).hexdigest()[:16],16)
    rng=random.Random(seed)
    delay=rng.randint(max(3,lo),max(max(3,lo),hi))
    not_before=(now+timedelta(minutes=delay)).isoformat().replace("+00:00","Z")
    action_id=f"mio-reply-{reply_id}-{hashlib.sha256((reply_text+str(state.get('cycle'))).encode()).hexdigest()[:10]}"
    action={
      "action_id":action_id,"cycle":state.get("cycle"),"capability":"social.reply.send","status":"candidate",
      "policy":"public_conversation=autonomous_with_policy","requires_real_adapter_receipt":True,
      "reply_to_id":reply_id,"root_post_id":root_id,"target_handle":handle,"primary_text":reply_text,
      "position":position,"decision_reason":str(decision.get("reason") or "")[:300],
      "ir_id":ir.get("ir_id"),"ir_source_sha256":ir_binding["source_sha256"],
      "ir_authoring_context_sha256":ir_binding["context_sha256"],
      "not_before":not_before,"reasoning_executor":executor,
      "external_root":bool(selected.get("external_root")),
      "source_receipt_ref":selected.get("source_receipt_ref"),
      "search_receipt_ref":selected.get("search_receipt_ref")
    }
    while len(pending)>=12:
        terminal=next(i for i,x in enumerate(pending) if terminal_action(x))
        pending.pop(terminal)
    action["reasoning_receipt_ref"]=persist_reply_receipt(root,state,"CANDIDATE_CREATED","reply_intent_created",
        datetime.now(timezone.utc),action_id=action_id,position=position,**evidence)
    pending.append(action)
    state["pending_external_actions"]=pending
    state["last_reply_intent"]=action_id
    save(root/"pdca/state.json",state)
    out=root/"pdca/reply_intents"/f"{action_id}.json"
    save(out,{"schema":"agentos.persona-reply-intent/v1","created_at":now.isoformat().replace("+00:00","Z"),**action})
    print(json.dumps({"status":"CANDIDATE_CREATED","action_id":action_id,"position":position,"not_before":not_before},ensure_ascii=False))
    return 0

if __name__=="__main__": raise SystemExit(main())
