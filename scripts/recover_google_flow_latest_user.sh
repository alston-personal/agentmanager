#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -un)" != "ubuntu" ]; then
  echo "google_flow_recover=WRONG_USER"
  exit 2
fi

ROOT="$HOME/.local/share/agentos/gui-worker"
PY="$ROOT/venv/bin/python"
OUT_ROOT="/home/ubuntu/agent-data/artifacts/google-flow-recovery"
test -x "$PY"
mkdir -p "$OUT_ROOT"

"$PY" - "$OUT_ROOT" <<'PY'
from __future__ import annotations
import hashlib,json,sys,time
from datetime import datetime,timezone
from pathlib import Path
from playwright.sync_api import sync_playwright

PROJECT_URL="https://flow.google.com/project/7c7d201a-ee6f-40e1-aa4c-2309c9543237"
EXPECTED_MARKERS=("taipei","metro","umbrella","mio")
out_root=Path(sys.argv[1])
stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
run_dir=out_root/stamp
run_dir.mkdir(parents=True,exist_ok=True)

print("google_flow_recover_stage=CONNECT_CDP",flush=True)
with sync_playwright() as p:
    browser=p.chromium.connect_over_cdp("http://127.0.0.1:9222",timeout=10000)
    ctx=browser.contexts[0]
    page=next((x for x in ctx.pages if PROJECT_URL in str(x.url or "")),None)
    if page is None:
        page=next((x for x in ctx.pages if "flow.google.com" in str(x.url or "")),None)
    if page is None:
        page=ctx.new_page()
    if PROJECT_URL not in str(page.url or ""):
        page.goto(PROJECT_URL,wait_until="domcontentloaded",timeout=60000)
        page.wait_for_timeout(5000)
    print("google_flow_recover_stage=FLOW_LOADED",flush=True)
    print("google_flow_recover_url="+str(page.url or "")[:500])

    # Surface bounded controls for Google auth/security interstitials.
    host=(page.url.split("/")[2] if "://" in str(page.url or "") else "")
    if "myaccount.google.com" in host or "accounts.google.com" in host:
        controls=[]
        for sel in ("button","a","input"):
            loc=page.locator(sel)
            for i in range(min(loc.count(),40)):
                item=loc.nth(i)
                try:
                    if not item.is_visible(timeout=100):
                        continue
                    label=(item.get_attribute("aria-label") or item.get_attribute("value") or item.inner_text(timeout=300) or "").strip()
                    if label:
                        controls.append((sel+":"+label)[:120])
                except Exception:
                    pass
        if controls:
            print("google_flow_recover_controls="+json.dumps(controls[:40],ensure_ascii=False,separators=(",",":")))
        # Do not mutate account-security settings. Attempt a clean direct
        # navigation back to Flow once; if Google redirects back here, require
        # human completion.
        try:
            page.goto(PROJECT_URL,wait_until="domcontentloaded",timeout=60000)
            page.wait_for_timeout(5000)
            redirected_host=(page.url.split("/")[2] if "://" in str(page.url or "") else "")
            print("google_flow_recover_stage=AUTH_INTERSTITIAL_BYPASS_ATTEMPT")
            print("google_flow_recover_url="+str(page.url or "")[:500])
            if "myaccount.google.com" not in redirected_host and "accounts.google.com" not in redirected_host:
                host=redirected_host
            else:
                print("google_flow_recover=AUTH_INTERSTITIAL")
                raise SystemExit(0)
        except SystemExit:
            raise
        except Exception:
            print("google_flow_recover=AUTH_INTERSTITIAL")
            raise SystemExit(0)

    # Never treat public landing/marketing demo reels as generated project output.
    # First, try to enter the authenticated Flow workspace without creating or
    # generating anything.
    try:
        controls=(page.get_by_role("button",name="Create with Google Flow")
                  .or_(page.get_by_role("button",name="Try in Google Flow")))
        if controls.count():
            controls.first.click(timeout=3000)
            page.wait_for_timeout(5000)
            print("google_flow_recover_stage=WORKSPACE_ENTRY")
            print("google_flow_recover_url="+str(page.url or "")[:500])
    except Exception:
        pass

    # Dismiss non-destructive onboarding / promo overlays that can intercept
    # project-card clicks. Never mutate account/project data here.
    for label in ("OK, got it","Got it","知道了","關閉橫幅","Close banner"):
        try:
            loc=page.get_by_role("button",name=label,exact=True)
            if loc.count() and loc.first.is_visible(timeout=300):
                loc.first.click(timeout=1500)
                page.wait_for_timeout(300)
        except Exception:
            pass

    # If recovery resumes directly inside a Flow project, surface bounded
    # project state before looking for media. This helps distinguish generation
    # failure / pending state / alternate result DOM from "no video".
    if "/project/" in str(page.url or ""):
        try:
            project_body=page.locator("body").inner_text(timeout=3000) or ""
            project_text=" ".join(project_body.split())[:900]
            if project_text:
                print("google_flow_recover_project_text="+project_text)
        except Exception:
            pass
        try:
            counts={
                "video":page.locator("video").count(),
                "img":page.locator("img").count(),
                "button":page.locator("button").count(),
            }
            print("google_flow_recover_project_media_counts="+json.dumps(counts,separators=(",",":")))
        except Exception:
            pass

    # Rain Exit recovery is now pinned to the exact known project and is
    # strictly read-only. Wait for the already-approved generation to surface.
    project_verified=False
    if PROJECT_URL in str(page.url or ""):
        try:
            body=(page.locator("body").inner_text(timeout=4000) or "")
        except Exception:
            body=""
        low=body.lower()
        project_verified=all(m in low for m in EXPECTED_MARKERS)
        print("google_flow_recover_project_prompt_match="+("YES" if project_verified else "NO"))
        if not project_verified:
            print("google_flow_recover=PROJECT_MISMATCH")
            raise SystemExit(0)

        deadline=time.monotonic()+900
        while time.monotonic()<deadline:
            vids_now=page.locator("video")
            found=False
            for i in range(min(vids_now.count(),20)):
                item=vids_now.nth(i)
                try:
                    if not item.is_visible(timeout=300):
                        continue
                    context=""
                    try:
                        context=str(item.evaluate("""el => {
                          let n=el;
                          for(let i=0;i<6 && n;i++,n=n.parentElement){
                            const t=(n.innerText||'').trim();
                            if(t) return t.slice(0,700);
                          }
                          return '';
                        }""") or "")
                    except Exception:
                        pass
                    cl=context.lower()
                    if any(x in cl for x in ("gemini omni flash","creative partner at every step","google flow agent")):
                        continue
                    found=True
                    break
                except Exception:
                    pass
            if found:
                print("google_flow_recover_stage=PROJECT_VIDEO_READY",flush=True)
                break
            try:
                body=(page.locator("body").inner_text(timeout=2500) or "").lower()
            except Exception:
                body=""
            if any(x in body for x in ("generation failed","couldn't generate","failed to generate","產生失敗","生成失敗","無法生成")):
                print("google_flow_recover=GENERATION_FAILED")
                raise SystemExit(0)
            page.wait_for_timeout(5000)
        else:
            print("google_flow_recover=GENERATION_PENDING_TIMEOUT")
            raise SystemExit(0)

    # Collect visible videos with bounded surrounding text so recovery can
    # distinguish a real project result from Flow's generic demo media.
    candidates_meta=[]
    vids=page.locator("video")
    for i in range(min(vids.count(),20)):
        item=vids.nth(i)
        try:
            if not item.is_visible(timeout=300):
                continue
            context=""
            try:
                context=str(item.evaluate("""el => {
                  let n=el;
                  for(let i=0;i<5 && n;i++,n=n.parentElement){
                    const t=(n.innerText||'').trim();
                    if(t) return t.slice(0,500);
                  }
                  return '';
                }""") or "")
            except Exception:
                pass
            candidates_meta.append({"index":i,"context":context[:500]})
        except Exception:
            pass

    if candidates_meta:
        print("google_flow_recover_video_candidates="+json.dumps(candidates_meta,ensure_ascii=False,separators=(",",":")))

    # Require project/workspace evidence. Generic Flow landing reels are invalid.
    page_text=""
    try:
        page_text=(page.locator("body").inner_text(timeout=2000) or "").lower()
    except Exception:
        pass
    project_markers=("rain exit","rain-exit","taipei","metro","umbrella","雨夜","捷運")
    matching=[]
    for meta in candidates_meta:
        low=meta["context"].lower()
        if any(x in low for x in ("gemini omni flash","creative partner at every step","google flow agent")):
            continue
        if project_verified or any(m in low for m in project_markers):
            matching.append(meta["index"])

    if not matching:
        controls=[]
        for sel in ("button","a","[role=button]"):
            loc=page.locator(sel)
            for i in range(min(loc.count(),60)):
                item=loc.nth(i)
                try:
                    if not item.is_visible(timeout=100):
                        continue
                    label=(item.get_attribute("aria-label") or item.inner_text(timeout=300) or "").strip()
                    href=(item.get_attribute("href") or "").strip()
                    if label or href:
                        controls.append((sel+":"+label+("|href="+href if href else ""))[:180])
                except Exception:
                    pass
        if controls:
            print("google_flow_recover_controls="+json.dumps(controls[:60],ensure_ascii=False,separators=(",",":")))

        projects=[]
        try:
            edits=page.get_by_role("button",name="編輯專案名稱")
            if edits.count()==0:
                edits=page.get_by_role("button",name="Edit project name")
            for i in range(min(edits.count(),20)):
                item=edits.nth(i)
                meta=item.evaluate("""el => {
                  let n=el.parentElement;
                  for(let depth=1; depth<10 && n; depth++,n=n.parentElement){
                    const text=(n.innerText||'').trim().replace(/\s+/g,' ').slice(0,260);
                    const directHref=n.getAttribute && n.getAttribute('href');
                    const a=(n.matches && n.matches('a[href]')) ? n : (n.querySelector ? n.querySelector('a[href]') : null);
                    const href=directHref || (a ? a.getAttribute('href') : '') || '';
                    const norm=text.toLowerCase();
                    if((href || text.length>4) &&
                       norm!=='edit' && norm!=='delete' &&
                       !text.includes('新增專案') && !text.includes('New project')){
                      return {depth,text,href};
                    }
                  }
                  return {depth:-1,text:'',href:''};
                }""")
                if isinstance(meta,dict):
                    projects.append(meta)
        except Exception:
            pass
        if projects:
            print("google_flow_recover_projects="+json.dumps(projects[:20],ensure_ascii=False,separators=(",",":")))

        project_dom=[]
        try:
            edits=page.get_by_role("button",name="編輯專案名稱")
            if edits.count()==0:
                edits=page.get_by_role("button",name="Edit project name")
            if edits.count():
                first=edits.first
                project_dom=first.evaluate("""el => {
                  const out=[];
                  let n=el;
                  for(let depth=0; depth<8 && n; depth++,n=n.parentElement){
                    out.push({
                      depth,
                      tag:(n.tagName||'').toLowerCase(),
                      role:n.getAttribute ? (n.getAttribute('role')||'') : '',
                      tabindex:n.getAttribute ? (n.getAttribute('tabindex')||'') : '',
                      cls:((n.className||'')+'').slice(0,160),
                      text:((n.innerText||'').trim().replace(/\s+/g,' ')).slice(0,220)
                    });
                  }
                  return out;
                }""")
        except Exception:
            pass
        if project_dom:
            print("google_flow_recover_project_dom="+json.dumps(project_dom,ensure_ascii=False,separators=(",",":")))

        # Rain Exit s01 was triggered around 2026-10-06 13:42 local time.
        # Prefer that exact recent project card; opening an existing project is
        # read-only and does not trigger generation.
        target_label=None
        for meta in projects:
            txt=str(meta.get("text") or "")
            if txt.startswith("10月 06 - 13:42") or txt.startswith("Oct 06 - 13:42"):
                target_label=txt.replace(" edit","").replace(" Edit","").strip()
                break
        if target_label:
            print("google_flow_recover_stage=OPEN_MATCHED_PROJECT")
            print("google_flow_recover_project_label="+target_label)
            opened=False
            try:
                cards=page.locator("flow-project-card")
                for i in range(min(cards.count(),20)):
                    card=cards.nth(i)
                    txt=(card.inner_text(timeout=800) or "").strip()
                    if target_label not in txt:
                        continue
                    box=card.bounding_box()
                    if box:
                        # Click the visual card body, away from edit/delete controls.
                        page.mouse.click(box["x"]+max(20,box["width"]*0.25),
                                         box["y"]+max(20,box["height"]*0.30))
                    else:
                        card.click(timeout=4000,position={"x":20,"y":20})
                    opened=True
                    break
            except Exception:
                opened=False
            if not opened:
                try:
                    card=page.locator(".project-card").filter(has_text=target_label).first
                    card.click(timeout=4000,position={"x":20,"y":20})
                    opened=True
                except Exception:
                    pass
            if not opened:
                print("google_flow_recover=PROJECT_OPEN_FAILED")
                raise SystemExit(0)
            page.wait_for_timeout(8000)
            print("google_flow_recover_url="+str(page.url or "")[:500])

            body=""
            try:
                body=(page.locator("body").inner_text(timeout=3000) or "")
            except Exception:
                pass
            low=body.lower()
            prompt_markers=("taipei","metro","umbrella","台北","捷運","雨傘","雨夜出口")
            prompt_hit=any(x in low for x in prompt_markers)
            print("google_flow_recover_project_prompt_match="+("YES" if prompt_hit else "NO"))

            vids=page.locator("video")
            project_candidates=[]
            for i in range(min(vids.count(),20)):
                item=vids.nth(i)
                try:
                    if not item.is_visible(timeout=300):
                        continue
                    context=""
                    try:
                        context=str(item.evaluate("""el => {
                          let n=el;
                          for(let i=0;i<6 && n;i++,n=n.parentElement){
                            const t=(n.innerText||'').trim();
                            if(t) return t.slice(0,700);
                          }
                          return '';
                        }""") or "")
                    except Exception:
                        pass
                    project_candidates.append({"index":i,"context":context[:700]})
                except Exception:
                    pass
            if project_candidates:
                print("google_flow_recover_video_candidates="+json.dumps(project_candidates,ensure_ascii=False,separators=(",",":")))

            # Bounded project-state evidence for generated-result recovery.
            try:
                project_text=" ".join((body or "").split())[:900]
                if project_text:
                    print("google_flow_recover_project_text="+project_text)
            except Exception:
                pass
            try:
                counts={
                    "video": page.locator("video").count(),
                    "img": page.locator("img").count(),
                    "button": page.locator("button").count(),
                }
                print("google_flow_recover_project_media_counts="+json.dumps(counts,separators=(",",":")))
            except Exception:
                pass
            project_controls=[]
            try:
                for sel in ("button","[role=button]"):
                    loc=page.locator(sel)
                    for i in range(min(loc.count(),50)):
                        item=loc.nth(i)
                        try:
                            if not item.is_visible(timeout=100):
                                continue
                            label=(item.get_attribute("aria-label") or item.inner_text(timeout=250) or "").strip()
                            if label:
                                project_controls.append((sel+":"+label)[:140])
                        except Exception:
                            pass
            except Exception:
                pass
            if project_controls:
                print("google_flow_recover_project_controls="+json.dumps(project_controls[:50],ensure_ascii=False,separators=(",",":")))

            chosen=None
            for meta in project_candidates:
                ctx_low=str(meta.get("context") or "").lower()
                if prompt_hit or any(x in ctx_low for x in prompt_markers):
                    chosen=meta["index"]
                    break
            if chosen is not None:
                video=vids.nth(chosen)
                print("google_flow_recover_stage=VIDEO_VISIBLE",flush=True)
            else:
                print("google_flow_recover=PROJECT_OPENED_NO_MATCHING_VIDEO")
                raise SystemExit(0)
        else:
            print("google_flow_recover=NO_MATCHING_PROJECT_VIDEO")
            raise SystemExit(0)

    video=vids.nth(matching[0])
    print("google_flow_recover_stage=VIDEO_VISIBLE",flush=True)
    src=str(video.get_attribute("src") or "")
    try:
        current_src=str(video.evaluate("(el) => el.currentSrc || el.src || ''") or "")
    except Exception:
        current_src=""
    try:
        source_src=str(video.locator("source").first.get_attribute("src") or "")
    except Exception:
        source_src=""
    candidates=[]
    for value in (current_src,src,source_src):
        if value and value not in candidates:
            candidates.append(value)
    print("google_flow_recover_video_scheme="+(("blob" if any(x.startswith("blob:") for x in candidates) else "http") if candidates else "none"))

    output=run_dir/"google-flow-recovered.mp4"
    downloaded=False

    # First try provider-backed HTTP(S) media URLs.
    for media_url in candidates:
        if not media_url.startswith(("http://","https://")):
            continue
        try:
            resp=ctx.request.get(media_url,timeout=120000)
            if resp.ok and len(resp.body()) >= 10000:
                output.write_bytes(resp.body())
                downloaded=True
                break
        except Exception:
            pass

    # If Flow exposes a blob: URL, ask Chromium itself to download that exact
    # already-generated media. This is read-only and does not trigger generation.
    if not downloaded:
        blob_url=next((x for x in candidates if x.startswith("blob:")),None)
        if blob_url:
            try:
                with page.expect_download(timeout=20000) as dl:
                    page.evaluate("""(u) => {
                      const a=document.createElement('a');
                      a.href=u; a.download='google-flow-recovered.mp4';
                      document.body.appendChild(a); a.click(); a.remove();
                    }""",blob_url)
                dl.value.save_as(str(output))
                downloaded=True
            except Exception:
                pass

    # Try visible download controls, including localized labels.
    if not downloaded:
        for pattern in ("Download","下載","Save","儲存"):
            try:
                loc=page.get_by_role("button",name=pattern,exact=False)
                if loc.count():
                    with page.expect_download(timeout=15000) as dl:
                        loc.first.click(timeout=3000)
                    dl.value.save_as(str(output))
                    downloaded=True
                    break
            except Exception:
                pass

    # Some Flow surfaces hide Download behind a more/options menu.
    if not downloaded:
        for pattern in ("More options","More","更多選項","更多"):
            try:
                loc=page.get_by_role("button",name=pattern,exact=False)
                if not loc.count():
                    continue
                loc.first.click(timeout=3000)
                page.wait_for_timeout(500)
                for dl_name in ("Download","下載","Save","儲存"):
                    dl_loc=page.get_by_role("menuitem",name=dl_name,exact=False)
                    if not dl_loc.count():
                        dl_loc=page.get_by_text(dl_name,exact=False)
                    if dl_loc.count():
                        with page.expect_download(timeout=15000) as dl:
                            dl_loc.first.click(timeout=3000)
                        dl.value.save_as(str(output))
                        downloaded=True
                        break
                if downloaded:
                    break
            except Exception:
                pass

    if not downloaded or not output.exists() or output.stat().st_size < 10000:
        controls=[]
        try:
            for sel in ("button","a"):
                loc=page.locator(sel)
                for i in range(min(loc.count(),30)):
                    item=loc.nth(i)
                    try:
                        if not item.is_visible(timeout=100):
                            continue
                        label=(item.get_attribute("aria-label") or item.inner_text(timeout=300) or "").strip()
                        if label:
                            controls.append((sel+":"+label)[:120])
                    except Exception:
                        pass
        except Exception:
            pass
        if controls:
            print("google_flow_recover_controls="+json.dumps(controls[:40],ensure_ascii=False,separators=(",",":")))
        print("google_flow_recover=VIDEO_VISIBLE_NOT_DOWNLOADED")
        raise SystemExit(0)
    raw=output.read_bytes()
    sha=hashlib.sha256(raw).hexdigest()
    print("google_flow_recover=PASS")
    print("google_flow_recover_output="+str(output))
    print("google_flow_recover_bytes="+str(len(raw)))
    print("google_flow_recover_sha256="+sha)
PY
