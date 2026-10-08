#!/usr/bin/env python3
import argparse, json, os
from datetime import datetime, timezone
from pathlib import Path

LABELS={
  "observe":("觀察一下","看看最近發生了什麼，先不急著做決定。","留意環境"),
  "wardrobe_plan":("想一下今天怎麼搭","從候選衣櫃裡整理一套虛擬搭配，不代表真的擁有或穿過。","穿搭"),
  "reflect":("整理一下最近的想法","把最近的事件重新想一遍，看看有沒有值得留下的變化。","整理想法"),
  "content_ideation":("想新的內容","從最近的經驗找一個自然的題目，不為了發文而硬發。","創作"),
  "review_social_feedback":("看看大家最近說了什麼","回頭看公開互動，判斷哪些值得繼續聊。","互動"),
  "rest":("休息一下","暫時降低活動，讓自己恢復一點。","休息"),
  "sleep":("睡覺中","現在是休息時段。","休息"),
}

def load(p):
    with open(p,"r",encoding="utf-8") as f:return json.load(f)

def receipts(path):
    out=[]
    if not path.exists(): return out
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            x=json.loads(line)
            if isinstance(x,dict): out.append(x)
        except Exception: pass
    return out

def activity_for(root,cycle,local_date):
    p=root/"pdca/activities"/local_date/f"cycle-{cycle}.json"
    if not p.exists(): return None
    try:return load(p)
    except Exception:return None

def public_item(r,a):
    intent=str((r.get("plan") or {}).get("selected_intent") or (a or {}).get("intent") or "")
    title,summary,focus=LABELS.get(intent,("最近有新的活動","澪留下了一筆新的自主活動紀錄。","日常"))
    local=str(r.get("local_time") or "")
    hhmm=local[11:16] if len(local)>=16 else ""
    check=r.get("check") or {}
    item={"cycle":int(r.get("cycle") or 0),"intent":intent,"title":title,"summary":summary,"time_label":hhmm,"focus_label":focus,
          "energy_before":check.get("energy_before"),"energy_after":check.get("energy_after"),
          "external_action_completed":bool(check.get("external_action_completed")),
          "activity_status":(a or {}).get("status") if isinstance(a,dict) else None,
          "activity_result":(a or {}).get("result") if isinstance(a,dict) else None,
          "cognitive_ir_status":((a or {}).get("cognitive_ir") or {}).get("projection_status") if isinstance(a,dict) else None,
          "external_receipt_ref":(a or {}).get("external_receipt_ref") if isinstance(a,dict) else None}
    if intent=="wardrobe_plan" and isinstance(a,dict):
        items=a.get("items") or []
        labels=[str(x.get("label") or "") for x in items if isinstance(x,dict) and x.get("label")]
        if labels:
            shown="、".join(labels[:3])
            item["summary"]=f"這次拿 {shown} 做了一套虛擬搭配提案；目前只代表想試，不代表真的買了或穿過。"
    elif intent=="reflect" and isinstance(a,dict):
        item["summary"]="整理最近發生的事與自己的反應，保留值得延續的方向。"
    elif intent=="observe" and isinstance(a,dict):
        snap=a.get("snapshot") or {}
        unseen=int(snap.get("unseen_events") or 0)
        item["summary"]="看看最近有沒有新的變化。" + (f" 這一輪注意到 {unseen} 個新事件。" if unseen else "")
    return item

def parse_ts(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z","+00:00"))
    except Exception:
        return None

def activity_health(root,state,now):
    cfg=load(root/"pdca/config.json")
    heartbeat=float(cfg.get("heartbeat_minutes") or 60)
    last_tick=parse_ts(state.get("last_tick_at"))
    age_minutes=None
    if last_tick is not None:
        if last_tick.tzinfo is None:
            last_tick=last_tick.replace(tzinfo=timezone.utc)
        age_minutes=max(0.0,(now.astimezone(timezone.utc)-last_tick.astimezone(timezone.utc)).total_seconds()/60.0)

    cycle=int(state.get("cycle") or 0)
    activity_ref=state.get("last_activity_receipt")
    projection_ref=state.get("last_ir_projection_receipt")
    activity_cycle=None
    projection_cycle=None

    if activity_ref:
        p=root/activity_ref
        if p.exists():
            try: activity_cycle=int(load(p).get("cycle") or 0)
            except Exception: pass
    if projection_ref:
        p=root/projection_ref
        if p.exists():
            try: projection_cycle=int(load(p).get("cycle") or 0)
            except Exception: pass

    cognitive_fresh=(activity_cycle==cycle and projection_cycle==cycle)
    stalled=(age_minutes is None or age_minutes > heartbeat*1.75)
    if stalled:
        status="STALLED"
        reason="heartbeat_overdue"
    elif not cognitive_fresh:
        status="DEGRADED"
        reason="cognitive_projection_stale"
    else:
        last_obs=state.get("last_social_observation") or {}
        obs_cycle=int(last_obs.get("cycle") or 0) if isinstance(last_obs,dict) else 0
        read_status=str(last_obs.get("read_status") or "") if isinstance(last_obs,dict) else ""
        if read_status and read_status not in ("PASS","NO_CHANGE"):
            status="DEGRADED"
            reason="social_capability_degraded"
        elif obs_cycle==cycle:
            status="ACTIVE"
            reason="cognitive_and_social_cycle_fresh"
        else:
            status="ALIVE_IDLE"
            reason="cognitive_cycle_fresh_no_current_external_activity"

    return {
      "status":status,
      "reason":reason,
      "cycle":cycle,
      "heartbeat_age_minutes":round(age_minutes,2) if age_minutes is not None else None,
      "heartbeat_budget_minutes":heartbeat,
      "activity_cycle":activity_cycle,
      "projection_cycle":projection_cycle,
      "cognitive_fresh":cognitive_fresh,
    }

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--persona-dir",required=True)
    ap.add_argument("--output",required=True)
    ap.add_argument("--html-output")
    args=ap.parse_args()
    root=Path(args.persona_dir)
    ir=load(root/"ir/current.json")
    state=load(root/"pdca/state.json")
    observation=state.get("last_social_observation") or {}
    allr=[]
    for p in sorted((root/"pdca/receipts").glob("*.jsonl")):
        allr.extend(receipts(p))
    auto=[r for r in allr if r.get("trigger")=="oracle_local_timer"]
    recent=[]
    for r in auto[-8:]:
        local=str(r.get("local_time") or "")
        day=local[:10] if len(local)>=10 else ""
        a=activity_for(root,int(r.get("cycle") or 0),day)
        recent.append(public_item(r,a))
    recent=list(reversed(recent))
    current=recent[0] if recent else {
      "intent":"waiting","title":"等待下一次自主活動",
      "summary":"自主生活循環已啟用；下一次由澪自己的 heartbeat 產生活動後會自動更新到這裡。",
      "focus_label":"自主運作中"
    }
    now=datetime.now().astimezone()
    health=activity_health(root,state,now)
    payload={
      "schema":"milkcat.persona-public-activity/v1",
      "character_id":"sunlake-milkcat-ai-001",
      "updated_at":now.isoformat(timespec="seconds"),
      "updated_label":f"更新於 {now.strftime('%m/%d %H:%M')}",
      "persona_revision":ir.get("revision"),
      "activity_count":len(auto),
      "autonomy_health":health,
      "social_observation":{k:observation.get(k) for k in
          ("observed_at","read_status","result","posts_scanned","replies_observed","fresh_replies")},
      "current":current,
      "recent":recent[:6],
      "privacy":{
        "public_projection":True,
        "contains_private_memory":False,
        "contains_internal_policy":False,
        "contains_credentials":False
      }
    }
    out=Path(args.output)
    out.parent.mkdir(parents=True,exist_ok=True)
    tmp=out.with_suffix(out.suffix+".tmp")
    tmp.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    os.chmod(tmp,0o644)
    os.replace(tmp,out)

    if args.html_output:
        html_out=Path(args.html_output)
        html_out.parent.mkdir(parents=True,exist_ok=True)
        html="""<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>澪｜活動紀錄</title>
<style>
:root{font-family:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:#171717;background:#fafafa}
body{margin:0}.wrap{max-width:860px;margin:auto;padding:28px 18px 64px}
h1{margin:0 0 6px;font-size:30px}.muted{color:#737373}.hero,.card{background:#fff;border:1px solid #e5e5e5;border-radius:18px}
.hero{padding:20px;margin:20px 0}.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin-top:14px}
.stat{padding:12px;background:#fafafa;border-radius:12px}.stat b{display:block;font-size:20px;margin-top:3px}
.timeline{display:grid;gap:12px}.card{padding:16px}.row{display:flex;justify-content:space-between;gap:12px}
.tag{font-size:12px;padding:4px 8px;border-radius:999px;background:#f1f5f9}.meta{font-size:13px;color:#737373;margin-top:8px;display:flex;gap:10px;flex-wrap:wrap}
@media(max-width:620px){.grid{grid-template-columns:1fr}.row{display:block}.tag{display:inline-block;margin-top:8px}}
</style>
</head>
<body><main class="wrap">
<h1>澪的活動紀錄</h1><div id="updated" class="muted">讀取中…</div>
<section id="hero" class="hero"><div class="muted">正在讀取 Activity IR…</div></section>
<h2>最近活動</h2><section id="timeline" class="timeline"></section>
</main>
<script>
const e=s=>String(s??"").replace(/[&<>"']/g,m=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[m]));
const f=v=>v===null||v===undefined?"—":v;
fetch("./activity.json",{cache:"no-store"}).then(r=>{if(!r.ok)throw Error();return r.json()}).then(d=>{
document.querySelector("#updated").textContent=d.updated_label||"";
const h=d.autonomy_health||{},s=d.social_observation||{},c=d.current||{};
document.querySelector("#hero").innerHTML='<div class="row"><div><div class="muted">現在</div><h2>'+e(c.title||"自主運作中")+'</h2><div>'+e(c.summary||"")+'</div></div><span class="tag">'+e(h.status||"UNKNOWN")+'</span></div><div class="grid"><div class="stat"><span class="muted">Cycle</span><b>'+f(h.cycle)+'</b></div><div class="stat"><span class="muted">活動總數</span><b>'+f(d.activity_count)+'</b></div><div class="stat"><span class="muted">Threads</span><b>'+e(s.read_status||"—")+'</b></div></div>';
document.querySelector("#timeline").innerHTML=(d.recent||[]).map(x=>'<article class="card"><div class="row"><div><strong>'+e(x.time_label||"")+'　'+e(x.title||x.intent)+'</strong><div>'+e(x.summary||"")+'</div></div><span class="tag">'+e(x.focus_label||x.intent||"")+'</span></div><div class="meta"><span>cycle '+f(x.cycle)+'</span><span>energy '+f(x.energy_before)+' → '+f(x.energy_after)+'</span><span>activity '+e(x.activity_status||"—")+'</span><span>IR '+e(x.cognitive_ir_status||"—")+'</span></div></article>').join("");
}).catch(()=>{document.querySelector("#hero").textContent="活動資料目前讀取失敗。"});
</script></body></html>"""
        tmp_html=html_out.with_suffix(html_out.suffix+".tmp")
        tmp_html.write_text(html,encoding="utf-8")
        os.chmod(tmp_html,0o644)
        os.replace(tmp_html,html_out)

    print(json.dumps({"mio_public_activity_publish":"PASS","output":str(out),"html_output":str(args.html_output or ""),"activity_count":len(auto),"persona_revision":ir.get("revision")},ensure_ascii=False))
    return 0

if __name__=="__main__":raise SystemExit(main())
