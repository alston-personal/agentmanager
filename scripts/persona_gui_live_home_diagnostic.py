"""Bounded Oracle GUI Threads homepage diagnostic; never infer login from page text.

Existing CDP contexts are left untouched. A disposable page is opened and
closed per port. No cookies/storage/network interception, no publish actions.
"""
import asyncio
import json
from datetime import datetime, timezone
from urllib.parse import urlsplit

PORTS=(9222,9223,9224)
HOME="https://www.threads.com/"

def classify(*, final_url, http_status, page_title, visible_login):
    parsed=urlsplit(final_url or "")
    if parsed.scheme!="https" or parsed.hostname not in ("www.threads.com","threads.com"):
        return "BLOCKED","NAVIGATION_NOT_THREADS"
    if http_status is not None and http_status>=400:
        return "BLOCKED","HTTP_ERROR"
    if visible_login:
        return "AUTH_REQUIRED","LOGIN_UI_PRESENT"
    return "UNVERIFIED","SIGNED_IN_IDENTITY_UNPROVEN"


def classify_profile_nav(hrefs):
    """A visible dedicated Profile nav is evidence, not proof of account ownership."""
    import re
    if not isinstance(hrefs,list):
        return "IDENTITY_UNVERIFIED",None
    candidates=set()
    for href in hrefs[:20]:
        if not isinstance(href,str):
            continue
        parsed=urlsplit(href)
        if parsed.scheme=="https" and parsed.hostname in ("www.threads.com","threads.com"):
            m=re.fullmatch(r"/@([A-Za-z0-9._]{1,40})/?",parsed.path)
            if m:
                candidates.add(m.group(1).lower())
    if len(candidates)!=1:
        return "IDENTITY_UNVERIFIED",None
    handle=next(iter(candidates))
    if handle!="mio.milkcat":
        return "ACCOUNT_MISMATCH",None
    return "PROFILE_NAV_MATCH_ONLY",handle

async def inspect_one(playwright,port):
    row={"port":port,"status":"BLOCKED","reason":"CDP_OR_NAVIGATION_UNAVAILABLE",
         "http_status":None,"identity_verified":False,"for_you_read_verified":False,
         "candidate_count":0,"write_performed":False}
    browser=None
    page=None
    try:
        browser=await asyncio.wait_for(playwright.chromium.connect_over_cdp(
            "http://127.0.0.1:%d"%port,timeout=12000),timeout=15)
        contexts=browser.contexts
        if not contexts:
            row["reason"]="NO_BROWSER_CONTEXT"
            return row
        page=await contexts[0].new_page()
        response=await page.goto(HOME,wait_until="domcontentloaded",timeout=25000)
        await page.wait_for_timeout(2500)
        # Only login prompts are used. Never treat page title/contents as
        # evidence of which account owns the authenticated browser context.
        login=await page.locator('input[type="password"]').count()>0
        status,reason=classify(final_url=page.url,
            http_status=response.status if response else None,
            page_title="",visible_login=login)
        row.update(status=status,reason=reason,
                   http_status=response.status if response else None)
        if status=="UNVERIFIED":
            # Use only visible dedicated Profile/個人檔案 navigation controls.
            # Never interpret arbitrary post/profile links as signed-in identity.
            links=await page.locator('a[aria-label="Profile"],a[aria-label="個人檔案"],a[aria-label="個人資料"],a[title="Profile"]').evaluate_all(
                "(els) => els.slice(0,20).map(a => a.href)")
            signal,handle=classify_profile_nav(links)
            row["account_signal"]=signal
            if signal=="ACCOUNT_MISMATCH":
                row.update(status="ACCOUNT_MISMATCH",reason="FOREIGN_PROFILE_NAV")
            elif signal=="PROFILE_NAV_MATCH_ONLY":
                row.update(status="UNVERIFIED",reason="PROFILE_NAV_MATCH_NEEDS_IDENTITY_RECEIPT")
                row["mio_profile_nav_seen"]=True
                # Snapshot external post links only; do not pretend this is an
                # authenticated for_you.read receipt or authorize interactions.
                links=await page.locator('a[href*="/post/"]').evaluate_all(
                    "(els) => els.slice(0,100).map(a => a.href)")
                import re
                urls=sorted(set(u for u in links if isinstance(u,str) and
                    re.fullmatch(r"https://www\\.threads\\.com/@[A-Za-z0-9._]{1,40}/post/[A-Za-z0-9_-]{1,40}",u) and
                    not u.lower().startswith("https://www.threads.com/@mio.milkcat/")))
                row["candidate_count"]=min(len(urls),20)
                row["candidate_urls"]=urls[:20]

    except Exception:
        row["reason"]="CDP_OR_NAVIGATION_UNAVAILABLE"
    finally:
        if page is not None:
            try: await page.close()
            except Exception: pass
        if browser is not None:
            try: await browser.close()
            except Exception: pass
    return row

async def main():
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        rows=[]
        for port in PORTS:
            rows.append(await inspect_one(p,port))
    report={"schema":"agentos.mio-gui-live-home-diagnostic/v1",
      "checked_at":datetime.now(timezone.utc).isoformat(),
      "status":"DIAGNOSTIC_ONLY","ports":rows,"identity_verified":False,
      "for_you_read_verified":False,"write_performed":False,
      "reply_allowed":False,"cookie_read_performed":False,
      "login_attempted":False,"anti_bot_bypass_used":False}
    print("mio_gui_live_home_receipt="+json.dumps(report,sort_keys=True))

if __name__=="__main__":
    asyncio.run(main())
