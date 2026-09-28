#!/usr/bin/env python3
import argparse, json, os
from datetime import datetime
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
    item={"cycle":int(r.get("cycle") or 0),"intent":intent,"title":title,"summary":summary,"time_label":hhmm,"focus_label":focus}
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

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--persona-dir",required=True)
    ap.add_argument("--output",required=True)
    args=ap.parse_args()
    root=Path(args.persona_dir)
    ir=load(root/"ir/current.json")
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
    payload={
      "schema":"milkcat.persona-public-activity/v1",
      "character_id":"sunlake-milkcat-ai-001",
      "updated_at":now.isoformat(timespec="seconds"),
      "updated_label":f"更新於 {now.strftime('%m/%d %H:%M')}",
      "persona_revision":ir.get("revision"),
      "activity_count":len(auto),
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
    print(json.dumps({"mio_public_activity_publish":"PASS","output":str(out),"activity_count":len(auto),"persona_revision":ir.get("revision")},ensure_ascii=False))
    return 0

if __name__=="__main__":raise SystemExit(main())
