#!/usr/bin/env python3
import argparse, glob, hashlib, json, os, random, re, shutil, subprocess, tempfile, time
from datetime import datetime, timedelta, timezone
from pathlib import Path

def load(path):
    with open(path,"r",encoding="utf-8") as f:
        return json.load(f)

def read_events(path,limit=80):
    out=[]
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            value=json.loads(line)
            if isinstance(value,dict):
                out.append(value)
        except Exception:
            pass
    return out[-limit:]

def discover_executor():
    patterns=[
      "/home/ubuntu/.antigravity-ide-server/extensions/anthropic.claude-code-*-linux-arm64/resources/native-binary/claude",
      "/home/ubuntu/.antigravity-ide-server/extensions/anthropic.claude-code-*/resources/native-binary/claude",
    ]
    found=[]
    for pattern in patterns:
        found += glob.glob(pattern)
    for path in sorted(set(found),reverse=True):
        if os.path.isfile(path) and os.access(path,os.X_OK):
            return [path,"--bare","--print","--output-format","text","--effort","low"]
    return None

def discover_gemini_executor():
    path="/home/ubuntu/.local/bin/gemini"
    return path if os.path.isfile(path) and os.access(path,os.X_OK) else None

def discover_codex_executor():
    # Same executable candidates as the existing Codex provider's discovery.
    for path in ("/home/ubuntu/.local/bin/codex","/home/ubuntu/.npm-global/bin/codex",
                 "/usr/local/bin/codex","/usr/bin/codex"):
        if os.path.isfile(path) and os.access(path,os.X_OK):
            return path
    return shutil.which("codex")

def extract_json(text):
    text=text.strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    m=re.search(r"\{.*\}",text,re.S)
    if not m:
        raise ValueError("executor_json_missing")
    return json.loads(m.group(0))

def failure_class(stderr, stdout=""):
    """Classify locally; never persist provider output, prompts or credentials."""
    if isinstance(stderr, bytes):
        stderr=stderr.decode("utf-8",errors="replace")
    error_text=str(stderr or "")
    # Gemini can report an error in JSON rather than stderr. Successful response
    # text is intentionally excluded: its topics are not diagnostic evidence.
    try:
        envelope=json.loads(stdout or "{}")
        if isinstance(envelope,dict) and isinstance(envelope.get("error"),(dict,str)):
            error_text+="\n"+json.dumps(envelope["error"],ensure_ascii=False)
    except (ValueError,TypeError):
        pass
    value=error_text.casefold()
    signatures=(
      ("OAUTH_CLIENT_UNSUPPORTED",("ineligibletiererror","unsupported_client","this client is no longer supported","migrate to antigravity")),
      ("CLI_CONTRACT",("unknown argument","unknown option","unrecognized option","invalid option","invalid values for argument")),
      ("RATE_LIMITED",("rate limit","too many requests","quota","resource_exhaust","resourceexhaust")),
      ("AUTH_REQUIRED",("authentication required","not authenticated","unauthorized","invalid_grant","sign in","log in","reauth","credential")),
      ("NETWORK",("network is unreachable","enotfound","eai_again","connection reset","socket hang up","etimedout","fetch failed")),
      ("CONFIG_ERROR",("fatalconfigerror","invalid configuration","failed to load settings","config error")),
      ("WORKSPACE_TRUST_REQUIRED",("workspace trust","folder trust","not trusted","trust this folder")),
      ("NODE_INCOMPATIBLE",("unsupported engine","ebadengine","requires node","node version")),
      ("HOOK_ERROR",("hook failed","hook error")),
      ("MCP_ERROR",("mcp server","mcp connection")),
    )
    return next((name for name,tokens in signatures if any(x in value for x in tokens)),"UNKNOWN_NONZERO")

def reasoning_attempt(provider, started, status, *, result=None, error=None):
    attempt={"provider":provider,"status":status,
             "elapsed_ms":max(0,round((time.monotonic()-started)*1000))}
    if result is not None:
        attempt["returncode"]=result.returncode
    if status=="NONZERO":
        attempt["failure_class"]=failure_class(result.stderr,result.stdout)
    elif status=="TIMEOUT":
        attempt["failure_class"]="TIMEOUT"
        hint=failure_class(getattr(error,"stderr",None))
        if hint!="UNKNOWN_NONZERO":
            attempt["failure_hint"]=hint
    elif status in ("INVALID_OUTPUT","UNAVAILABLE"):
        attempt["failure_class"]=status
    return attempt

def extract_decision(text):
    value=extract_json(text)
    if not isinstance(value,dict) or type(value.get("should_post")) is not bool or type(value.get("human_required")) is not bool:
        raise ValueError("executor_decision_invalid")
    if not isinstance(value.get("post_text"),str) or not isinstance(value.get("reason"),str):
        raise ValueError("executor_decision_invalid")
    return value

def safe_liveness_fallback(growth, state):
    lanes=growth.get("current_topic_lanes") if isinstance(growth.get("current_topic_lanes"),list) else []
    options=[]
    joined=" ".join(str(x) for x in lanes)
    if "穿搭" in joined:
        options.append("二選一：一眼就覺得好看，還是穿一整天都舒服？如果只能留一個標準，你選哪個？")
    if "日常" in joined or "週末" in joined:
        options.append("你有沒有那種：明明想休息，真的空下來又開始想找事做的時候？")
    if "貓" in joined or "小動物" in joined:
        options.append("如果一隻貓一直盯著你看，你第一個念頭會是：牠喜歡我，還是牠在評分我？")
    if not options:
        options.append("最近有沒有一個很小、但莫名讓你改變想法的瞬間？")
    cycle=int(state.get("cycle") or 0)
    return options[cycle % len(options)]

def persist_reasoning_receipt(root, state, attempts, status, now, *, fallback_used=False):
    ref=f"pdca/post_reasoning/{now.strftime('%Y-%m-%d')}/{now.strftime('%H%M%S')}.json"
    receipt={
      "schema":"agentos.persona-post-reasoning-receipt/v1",
      "timestamp":now.isoformat().replace("+00:00","Z"),
      "cycle":state.get("cycle"),
      "status":status,
      "attempts":attempts,
      "fallback_used":bool(fallback_used),
      "generator_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
      "diagnostic_contract":"sanitized-failure-class/v1"
    }
    path=root/ref
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    state["last_post_reasoning_receipt"]=ref
    return ref

def safe_post_text(text):
    if not isinstance(text,str):
        return False
    s=text.strip()
    if not s or len(s)>500:
        return False
    if "http://" in s or "https://" in s:
        return False
    if len(re.findall(r"[😀-🙏🌀-🫿]",s))>3:
        return False
    return True

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--persona-dir",required=True)
    args=ap.parse_args()
    root=Path(args.persona_dir)
    state=load(root/"pdca/state.json")
    ir=load(root/"ir/current.json")
    persona=load(root/"persona_state.json")
    cfg=load(root/"pdca/config.json")
    events=read_events(root/"events/events.jsonl")

    growth=cfg.get("growth_mode",{}) if isinstance(cfg.get("growth_mode"),dict) else {}
    posting_liveness=growth.get("posting_liveness",{}) if isinstance(growth.get("posting_liveness"),dict) else {}
    forced_consider_hours=float(posting_liveness.get("forced_consider_after_hours",30))
    forced_no_publish_streak=int(posting_liveness.get("forced_consider_after_no_publish_streak",3))
    now_utc=datetime.now(timezone.utc)
    todays_posts=[]
    for e in events:
        if e.get("type") not in ("post.sent","post.published"): continue
        ts=str(e.get("timestamp") or "")
        try:
            dt=datetime.fromisoformat(ts.replace("Z","+00:00"))
        except Exception:
            continue
        if dt.astimezone().date()==now_utc.astimezone().date():
            todays_posts.append(dt.astimezone(timezone.utc))
    todays_posts.sort()
    all_posts=[]
    for e in events:
        if e.get("type") not in ("post.sent","post.published"): continue
        ts=str(e.get("timestamp") or "")
        try:
            dt=datetime.fromisoformat(ts.replace("Z","+00:00"))
        except Exception:
            continue
        all_posts.append(dt.astimezone(timezone.utc))
    all_posts.sort()
    last_successful_post=all_posts[-1] if all_posts else None
    silence_hours=((now_utc-last_successful_post).total_seconds()/3600.0) if last_successful_post else 999.0
    no_publish_streak=int(state.get("post_no_publish_streak",0) or 0)
    target_raw=growth.get("daily_post_target")
    max_raw=growth.get("daily_post_max")
    gap_raw=growth.get("minimum_post_gap_minutes")
    daily_target=int(target_raw) if isinstance(target_raw,(int,float)) and not isinstance(target_raw,bool) else None
    max_posts=int(max_raw) if isinstance(max_raw,(int,float)) and not isinstance(max_raw,bool) else None
    min_gap=int(gap_raw) if isinstance(gap_raw,(int,float)) and not isinstance(gap_raw,bool) else None
    if max_posts is not None and len(todays_posts)>=max_posts:
        print(json.dumps({"status":"NO_POST","reason":"daily_post_max_reached","posts_today":len(todays_posts)},ensure_ascii=False))
        return 0
    if todays_posts and min_gap is not None:
        gap=(now_utc-todays_posts[-1]).total_seconds()/60.0
        if gap < min_gap:
            print(json.dumps({"status":"DEFER","reason":"minimum_post_gap","gap_minutes":round(gap,1),"required":min_gap},ensure_ascii=False))
            return 0

    pending=list(state.get("pending_external_actions") or [])
    if any(x.get("capability")=="social.post.publish" and x.get("status") in ("candidate","in_progress")
           for x in pending if isinstance(x,dict)):
        print(json.dumps({"status":"SKIP","reason":"post_publish_already_pending"},ensure_ascii=False))
        return 0
    consider=next((x for x in pending if isinstance(x,dict) and x.get("capability")=="social.post.consider" and x.get("status")=="candidate"),None)
    if not consider:
        energy_now=float(state.get("energy_current",0))
        liveness_due=(silence_hours>=forced_consider_hours or no_publish_streak>=forced_no_publish_streak)
        if energy_now>0 and liveness_due and growth.get("enabled") is True:
            consider={
              "action_id":f"mio-social-c{state.get('cycle')}-post-consider",
              "cycle":state.get("cycle"),
              "capability":"social.post.consider",
              "status":"candidate",
              "reason":"posting liveness safety net",
              "policy":"routine_posts=autonomous_with_policy",
              "requires_real_adapter_receipt":True,
              "liveness_pressure":True
            }
            pending.append(consider)
            state["pending_external_actions"]=pending[-12:]
            state["last_post_consider_at"]=now_utc.isoformat().replace("+00:00","Z")
            tmp=root/"pdca/state.json.tmp"
            tmp.write_text(json.dumps(state,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
            os.replace(tmp,root/"pdca/state.json")
        else:
            print(json.dumps({"status":"NO_CANDIDATE"},ensure_ascii=False))
            return 0
    activity_ref=str(state.get("last_activity_receipt") or "")
    activity={}
    if activity_ref:
        p=root/activity_ref
        if p.exists():
            activity=load(p)

    recent=[]
    for e in events[-20:]:
        if e.get("type") not in ("post.sent","post.published","reply.observed","reply.sent","wardrobe.window_shopping","pdca.activity.completed"):
            continue
        recent.append({
          "type":e.get("type"),
          "timestamp":e.get("timestamp"),
          "text":str(e.get("text") or e.get("summary") or "")[:240],
          "author":e.get("author_handle") or e.get("username"),
          "source_object_id":e.get("source_object_id") or e.get("object_id")
        })

    claude_executor=discover_executor()
    gemini_executor=discover_gemini_executor()
    codex_executor=discover_codex_executor()
    if not claude_executor and not gemini_executor and not codex_executor:
        persist_reasoning_receipt(root,state,[],"UNAVAILABLE",datetime.now(timezone.utc))
        tmp=root/"pdca/state.json.tmp"
        tmp.write_text(json.dumps(state,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        os.replace(tmp,root/"pdca/state.json")
        print(json.dumps({"status":"DEFER","reason":"persona_reasoning_executor_unavailable"},ensure_ascii=False))
        return 0

    current_self=ir.get("current_self") if isinstance(ir.get("current_self"),dict) else {}
    energy_state=persona.get("energy") if isinstance(persona.get("energy"),dict) else {}
    autonomy=persona.get("autonomy") if isinstance(persona.get("autonomy"),dict) else {}
    contract={
      "current_ir":{
        "ir_id":ir.get("ir_id"),
        "voice":current_self.get("voice"),
        "interaction_principles":current_self.get("interaction_principles"),
        "interests_with_evidence":current_self.get("interests_with_evidence"),
        "uncertainties":current_self.get("uncertainties")
      },
      "persona":{
        "voice":persona.get("voice"),
        "routine_posts_autonomy":autonomy.get("routine_posts"),
        "energy":{
          "current":state.get("energy_current",energy_state.get("current")),
          "decision_thresholds":energy_state.get("decision_thresholds")
        }
      },
      "pdca":{
        "cycle":state.get("cycle"),
        "focus":state.get("current_focus"),
        "consider_reason":consider.get("reason"),
        "activity_intent":activity.get("intent") if isinstance(activity,dict) else None,
        "activity_result":activity.get("result") if isinstance(activity,dict) else None
      },
      "growth_mode":{
        "enabled":growth.get("enabled"),
        "phase":growth.get("phase"),
        "primary_objective":growth.get("primary_objective"),
        "current_topic_lanes":growth.get("current_topic_lanes"),
        "content_rules":growth.get("content_rules"),
        "scheduling_policy":growth.get("scheduling_policy")
      },
      "growth_context":{
        "posts_today":len(todays_posts),
        "daily_target":daily_target,
        "daily_max":max_posts,
        "minimum_gap_minutes":min_gap,
        "silence_hours":round(silence_hours,1),
        "post_no_publish_streak":no_publish_streak,
        "posting_liveness_required": bool(consider.get("liveness_pressure")) or silence_hours>=30 or no_publish_streak>=3
      },
      "recent_verified_events":recent
    }

    prompt="""You are deciding whether Mio should publish one routine Threads post now.
The JSON context below is authoritative. Do not invent real-world experiences, locations, purchases, photos, meetings, weather, feelings caused by events, or relationship history that are not supported by the context.
A post may be based on verified recent events, a clearly labeled internal reflection, a question, or a small thought. Avoid repetitive generic inspirational copy.
When growth_mode.enabled is true and phase is reach_first, optimize for qualified discovery: the opening should contain a concrete hook, contrast, tension, surprising angle, or very easy-to-answer question. Prefer topic lanes that already have interaction evidence. Do not use clickbait that misrepresents the content. Do not write like a marketer. The post must still sound like Mio.
Mio is allowed to make routine public posts autonomously under policy, but commercial claims, payments, contracts, identity changes, private data, or unsupported real-world claims require no post.
If growth_context.posting_liveness_required is true, prolonged silence has become a liveness risk. In that case, prefer producing one safe, modest post candidate based on a question, internal reflection, or verified context. Do not return NO_POST merely because nothing dramatic happened. Return should_post=false only for a concrete blocker such as policy/human-required content, unsafe/unsupported claims, or clearly inadequate context.
Use natural Traditional Chinese. Keep it concise and human-like. Use 0-2 emoji unless the content strongly benefits from more. Do not mention internal systems, IR, PDCA, policies, or that a model generated the text.
Choose whether this post BENEFITS from an image. It is equally valid to choose text only. For an image, choose existing_verified only when a known asset with provenance is in context; otherwise choose generate. Never pretend a generated image is a real-life photograph or invent a real-life event. A generated image containing Mio must use her canonical realistic identity/reference and require likeness review.
Return ONLY one JSON object with exactly these keys:
{"should_post":true|false,"human_required":true|false,"reason":"short internal reason","post_text":"public text or empty","image_decision":"none|existing_verified|generate","image_reason":"short reason","image_prompt":"prompt or empty","image_asset_ref":"verified asset reference or empty"}
Context:
"""+json.dumps(contract,ensure_ascii=False)

    decision=None
    reasoning_executor=None
    attempts=[]
    if claude_executor:
        started=time.monotonic()
        try:
            result=subprocess.run([*claude_executor,prompt],cwd="/home/ubuntu/agentmanager",
                                  stdin=subprocess.DEVNULL,text=True,capture_output=True,timeout=45)
            if result.returncode==0:
                try:
                    decision=extract_decision(result.stdout)
                    reasoning_executor="antigravity_claude"
                    attempts.append(reasoning_attempt("claude",started,"PASS",result=result))
                except Exception:
                    attempts.append(reasoning_attempt("claude",started,"INVALID_OUTPUT",result=result))
            else:
                attempts.append(reasoning_attempt("claude",started,"NONZERO",result=result))
        except subprocess.TimeoutExpired as error:
            attempts.append(reasoning_attempt("claude",started,"TIMEOUT",error=error))
        except OSError:
            attempts.append(reasoning_attempt("claude",started,"UNAVAILABLE"))

    if decision is None and gemini_executor:
        started=time.monotonic()
        try:
            with tempfile.TemporaryDirectory(prefix="mio-post-gemini-") as td:
                temp=Path(td)
                cli_home=temp/"cli-home"
                settings=cli_home/".gemini"
                settings.mkdir(parents=True,exist_ok=True)
                (settings/"settings.json").write_text(json.dumps({
                    "security":{"auth":{"selectedType":"oauth-personal"}},
                    "hooksConfig":{"enabled":False},
                    "skills":{"enabled":False},
                })+"\n",encoding="utf-8")
                source=Path("/home/ubuntu/.gemini")
                for name in ("oauth_creds.json","google_accounts.json"):
                    src=source/name
                    if src.exists():
                        (settings/name).symlink_to(src)
                env={**os.environ,
                     "HOME":"/home/ubuntu",
                     "USER":"ubuntu",
                     "CI":"1",
                     "GEMINI_CLI_HOME":str(cli_home),
                     "PATH":"/home/ubuntu/.local/bin:/home/ubuntu/.local/share/agentos/npm-global/bin:"+os.environ.get("PATH","/usr/local/bin:/usr/bin:/bin")}
                result=subprocess.run([
                    gemini_executor,"-p",prompt,"--approval-mode","plan","--skip-trust",
                    "--output-format","json"
                ],cwd=str(temp),stdin=subprocess.DEVNULL,text=True,capture_output=True,timeout=60,env=env)
                if result.returncode==0:
                    try:
                        envelope=json.loads(result.stdout or "{}")
                        response=str(envelope.get("response") or "") if isinstance(envelope,dict) else ""
                        decision=extract_decision(response)
                        reasoning_executor="gemini_cli"
                        attempts.append(reasoning_attempt("gemini",started,"PASS",result=result))
                    except Exception:
                        attempts.append(reasoning_attempt("gemini",started,"INVALID_OUTPUT",result=result))
                else:
                    attempts.append(reasoning_attempt("gemini",started,"NONZERO",result=result))
        except subprocess.TimeoutExpired as error:
            attempts.append(reasoning_attempt("gemini",started,"TIMEOUT",error=error))
        except OSError:
            attempts.append(reasoning_attempt("gemini",started,"UNAVAILABLE"))

    if decision is None and codex_executor:
        started=time.monotonic()
        try:
            with tempfile.TemporaryDirectory(prefix="mio-post-codex-") as td:
                temp=Path(td)
                workspace=temp/"workspace"
                workspace.mkdir()
                cli_home=temp/"cli-home"
                cli_home.mkdir(mode=0o700)
                # Reuse OAuth without reading or serializing credential contents.
                # Keep global hooks, MCP servers, plugins and repo instructions
                # out of this text-only authoring task.
                source=Path(os.environ.get("CODEX_HOME") or "/home/ubuntu/.codex")
                auth=source/"auth.json"
                if auth.is_file():
                    (cli_home/"auth.json").symlink_to(auth)
                (cli_home/"config.toml").write_text(
                    'web_search = "disabled"\n[features]\nshell_tool = false\napps = false\n',
                    encoding="utf-8")
                answer=temp/"answer.json"
                env={**os.environ,"CODEX_HOME":str(cli_home)}
                result=subprocess.run([
                    codex_executor,"-a","never","exec","--skip-git-repo-check",
                    "--sandbox","read-only","--color","never","--ephemeral",
                    "-C",str(workspace),"--output-last-message",str(answer),prompt
                ],cwd=str(workspace),stdin=subprocess.DEVNULL,text=True,
                  capture_output=True,timeout=60,env=env)
                if result.returncode==0:
                    try:
                        response=answer.read_text(encoding="utf-8") if answer.is_file() else result.stdout
                        decision=extract_decision(response)
                        reasoning_executor="codex_cli"
                        attempts.append(reasoning_attempt("codex",started,"PASS",result=result))
                    except (OSError,ValueError,TypeError):
                        attempts.append(reasoning_attempt("codex",started,"INVALID_OUTPUT",result=result))
                else:
                    attempts.append(reasoning_attempt("codex",started,"NONZERO",result=result))
        except subprocess.TimeoutExpired as error:
            attempts.append(reasoning_attempt("codex",started,"TIMEOUT",error=error))
        except OSError:
            attempts.append(reasoning_attempt("codex",started,"UNAVAILABLE"))

    if decision is None:
        liveness_required=bool(consider.get("liveness_pressure")) or silence_hours>=forced_consider_hours or no_publish_streak>=forced_no_publish_streak
        if liveness_required:
            fallback_text=safe_liveness_fallback(growth,state)
            decision={
              "should_post":True,
              "human_required":False,
              "reason":"provider failover exhausted; safe liveness fallback",
              "post_text":fallback_text
            }
            reasoning_executor="safe_liveness_fallback"
            persist_reasoning_receipt(root,state,attempts,"FALLBACK",datetime.now(timezone.utc),fallback_used=True)
        else:
            persist_reasoning_receipt(root,state,attempts,"DEFER",datetime.now(timezone.utc))
            state["pending_external_actions"]=pending[-12:]
            tmp=root/"pdca/state.json.tmp"
            tmp.write_text(json.dumps(state,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
            os.replace(tmp,root/"pdca/state.json")
            print(json.dumps({"status":"DEFER","reason":"persona_reasoning_exhausted","attempts":attempts},ensure_ascii=False))
            return 0
    else:
        persist_reasoning_receipt(root,state,attempts,"PASS",datetime.now(timezone.utc))

    should=bool(decision.get("should_post"))
    human=bool(decision.get("human_required"))
    text=str(decision.get("post_text") or "").strip()
    reason=str(decision.get("reason") or "")[:300]
    image_mode=str(decision.get("image_decision") or "none")
    if image_mode not in ("none","existing_verified","generate"):
        image_mode="none"
    image_reason=str(decision.get("image_reason") or "")[:300]
    image_prompt=str(decision.get("image_prompt") or "").strip()[:1500]
    image_asset_ref=str(decision.get("image_asset_ref") or "").strip()
    if image_mode=="generate" and not image_prompt:
        image_mode="none"
        image_reason="missing image prompt; text-only"
    if image_mode=="existing_verified" and not image_asset_ref:
        image_mode="none"
        image_reason="missing verified asset; text-only"
    if human or not should:
        consider["status"]="completed"
        consider["completed_at"]=datetime.now(timezone.utc).isoformat().replace("+00:00","Z")
        consider["decision"]="no_post"
        consider["decision_reason"]=reason
        state["post_no_publish_streak"]=no_publish_streak+1
        state["last_post_consider_at"]=datetime.now(timezone.utc).isoformat().replace("+00:00","Z")
        state["pending_external_actions"]=pending[-12:]
        tmp=root/"pdca/state.json.tmp"
        tmp.write_text(json.dumps(state,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        os.replace(tmp,root/"pdca/state.json")
        print(json.dumps({"status":"NO_POST","human_required":human,"reason":reason},ensure_ascii=False))
        return 0
    if not safe_post_text(text):
        print(json.dumps({"status":"DEFER","reason":"post_text_guard_failed"},ensure_ascii=False))
        return 0

    now=datetime.now(timezone.utc)
    latency=persona.get("temporal_behavior",{}).get("post_latency",{}).get("typical_minutes",[5,25])
    try:
        lo,hi=int(latency[0]),int(latency[-1])
    except Exception:
        lo,hi=5,25
    seed=int(hashlib.sha256(f"{state.get('cycle')}|{ir.get('ir_id')}|{text}".encode()).hexdigest()[:16],16)
    rng=random.Random(seed)
    delay=rng.randint(max(3,lo),max(max(3,lo),hi))
    not_before=(now+timedelta(minutes=delay)).isoformat().replace("+00:00","Z")
    action_id=f"mio-post-c{state.get('cycle')}-{hashlib.sha256(text.encode()).hexdigest()[:10]}"
    action={
      "action_id":action_id,
      "cycle":state.get("cycle"),
      "capability":"social.post.publish",
      "status":"candidate",
      "policy":"routine_posts=autonomous_with_policy",
      "requires_real_adapter_receipt":True,
      "primary_text":text,
      "decision_reason":reason,
      "media_intent":{"mode":image_mode,"reason":image_reason,
                      "prompt":image_prompt if image_mode=="generate" else None,
                      "source_ref":image_asset_ref if image_mode=="existing_verified" else None,
                      "status":"not_requested" if image_mode=="none" else "awaiting_asset_and_validation",
                      "canonical_identity_required":image_mode=="generate",
                      "requires_provenance":image_mode!="none",
                      "requires_verified_media_receipt":image_mode!="none"},
      "ir_id":ir.get("ir_id"),
      "not_before":not_before,
      "reasoning_executor":reasoning_executor,
      "reasoning_receipt_ref":state["last_post_reasoning_receipt"]
    }
    consider["status"]="completed"
    consider["completed_at"]=now.isoformat().replace("+00:00","Z")
    consider["decision"]="publish_candidate_created"
    consider["publish_action_id"]=action_id
    pending.append(action)
    state["pending_external_actions"]=pending[-12:]
    state["last_post_intent"]=action_id
    state["post_no_publish_streak"]=0
    state["last_post_consider_at"]=now.isoformat().replace("+00:00","Z")
    tmp=root/"pdca/state.json.tmp"
    tmp.write_text(json.dumps(state,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    os.replace(tmp,root/"pdca/state.json")

    out=root/"pdca/post_intents"/f"{action_id}.json"
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps({
      "schema":"agentos.persona-post-intent/v1",
      "created_at":now.isoformat().replace("+00:00","Z"),
      **action
    },ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    if image_mode != "none":
        # Source-of-truth media task for a dedicated image executor. This is an
        # intent, not evidence that any image was generated or uploaded.
        request={
          "schema":"agentos.persona-media-request/v1",
          "action_id":action_id,
          "persona_id":state.get("persona_id"),
          "ir_id":ir.get("ir_id"),
          "created_at":now.isoformat().replace("+00:00","Z"),
          "status":"awaiting_media_executor",
          "mode":image_mode,
          "source_ref":image_asset_ref if image_mode=="existing_verified" else None,
          "generation_prompt":image_prompt if image_mode=="generate" else None,
          "canonical_visual_anchor":"visual_anchor_spec.json",
          "visual_policy":"visual_content_policy.json",
          "required_manifest_schema":"milkcat.image-manifest/v2",
          "required_validation":"validate_mio_visual_manifest.py",
          "required_media_publish_receipt":True,
          "text":text
        }
        request_path=root/"pdca/media_requests"/f"{action_id}.json"
        request_path.parent.mkdir(parents=True,exist_ok=True)
        request_path.write_text(json.dumps(request,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        action["media_intent"]["request_ref"]=str(request_path.relative_to(root))
        state["pending_external_actions"]=pending[-12:]
        tmp=root/"pdca/state.json.tmp"
        tmp.write_text(json.dumps(state,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        os.replace(tmp,root/"pdca/state.json")
        out.write_text(json.dumps({"schema":"agentos.persona-post-intent/v1",
          "created_at":now.isoformat().replace("+00:00","Z"),**action},
          ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"status":"CANDIDATE_CREATED","action_id":action_id,"not_before":not_before},ensure_ascii=False))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
