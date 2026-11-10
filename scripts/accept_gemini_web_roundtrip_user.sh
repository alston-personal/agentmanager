#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -un)" != "ubuntu" ]; then
  echo "gemini_web_roundtrip_acceptance=WRONG_USER" >&2
  exit 2
fi

ROOT="$HOME/.local/share/agentos/gui-worker"
PY="$ROOT/venv/bin/python"
test -x "$PY"

"$PY" - <<'PY'
from __future__ import annotations
import json
import re
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from playwright.sync_api import sync_playwright

CDP='http://127.0.0.1:9222'
PARTICIPANT_ID='participant://agent/gemini-web'
safe=PARTICIPANT_ID.replace('://','__').replace('/','_')
state_path=Path('/home/ubuntu/agent-data/runtime/participant-enrollment') / f'{safe}-pending.json'
state=None
if state_path.exists():
    candidate=json.loads(state_path.read_text(encoding='utf-8'))
    expires=str(candidate.get('expires_at') or '')
    try:
        expiry=datetime.fromisoformat(expires.replace('Z','+00:00')).astimezone(timezone.utc)
    except Exception:
        expiry=datetime.fromtimestamp(0,tz=timezone.utc)
    if expiry > datetime.now(timezone.utc) and candidate.get('status') == 'pending':
        state=candidate

if state:
    request_id=str(state['request_id'])
    challenge=str(state['challenge'])
    protocol=f"agentos-participant/{state['negotiated_protocol']}"
    expected={
        'request_id':request_id,
        'participant_id':PARTICIPANT_ID,
        'challenge':challenge,
        'protocol':protocol,
        'ack':'ACCEPT',
    }
    PROMPT=(
        "AgentOS ONE enrollment challenge. "
        "You previously requested hosted Participant onboarding. "
        "If you still accept joining as participant://agent/gemini-web under the negotiated protocol, "
        "reply with exactly this JSON object and no markdown or explanation:\n"
        + json.dumps(expected,ensure_ascii=False,separators=(',',':'))
    )
    marker=challenge
    mode='participant-enrollment'
else:
    PROMPT='AgentOS Gemini bridge smoke test. Reply with exactly: AGENTOS_GEMINI_BRIDGE_OK'
    marker='AGENTOS_GEMINI_BRIDGE_OK'
    mode='smoke'

composer_selectors=[
    'rich-textarea div[contenteditable="true"]',
    'textarea[aria-label*="prompt" i]',
    '[contenteditable="true"][aria-label*="prompt" i]',
    'div.ql-editor[contenteditable="true"]',
    'textarea',
    '[contenteditable="true"]',
]

def first_visible(page,selectors):
    for selector in selectors:
        try:
            loc=page.locator(selector)
            for i in range(min(loc.count(),12)):
                item=loc.nth(i)
                try:
                    if item.is_visible(timeout=300):
                        return item
                except Exception:
                    pass
        except Exception:
            pass
    return None

def harvest(page):
    rows=[]
    for selector in ('model-response','[data-test-id*="model-response"]','.model-response-text','message-content'):
        try:
            loc=page.locator(selector)
            for i in range(max(0,loc.count()-8),loc.count()):
                try:
                    value=loc.nth(i).inner_text(timeout=1000).strip()
                except Exception:
                    continue
                if value and value not in rows:
                    rows.append(value)
        except Exception:
            pass
    return rows

with sync_playwright() as p:
    browser=p.chromium.connect_over_cdp(CDP)
    if not browser.contexts:
        raise RuntimeError('gemini_roundtrip_no_browser_context')
    ctx=browser.contexts[0]
    pages=[x for x in ctx.pages if 'gemini.google.com' in str(x.url or '')]
    if not pages:
        raise RuntimeError('gemini_roundtrip_no_gemini_page')
    page=next((x for x in pages if first_visible(x,composer_selectors) is not None),pages[0])
    page.bring_to_front()
    composer=first_visible(page,composer_selectors)
    if composer is None:
        raise RuntimeError('gemini_roundtrip_composer_not_found')

    try:
        composer.fill(PROMPT)
    except Exception:
        composer.click()
        page.keyboard.press('ControlOrMeta+A')
        page.keyboard.type(PROMPT)

    print('gemini_web_roundtrip_inject=PASS')
    page.keyboard.press('Enter')
    print('gemini_web_roundtrip_submit=PASS')

    deadline=time.monotonic()+90
    response_text=''
    while time.monotonic()<deadline:
        rows=harvest(page)
        candidates=[x for x in rows if marker in x]
        if candidates:
            response_text=candidates[-1]
            break
        time.sleep(1)

    if not response_text:
        raise TimeoutError('gemini_roundtrip_response_timeout')

    print('gemini_web_roundtrip_response=PASS')
    print('gemini_web_roundtrip_harvest=PASS')

    if mode == 'participant-enrollment':
        match=re.search(r'\{.*\}', response_text, re.S)
        if not match:
            raise RuntimeError('participant_challenge_response_json_missing')
        response=json.loads(match.group(0))
        if response != expected:
            raise RuntimeError('participant_challenge_response_mismatch')

        payload=json.dumps({
            'request_id':state['request_id'],
            'claim_secret':state['claim_secret'],
            'response':response,
        },ensure_ascii=False).encode('utf-8')
        req=urllib.request.Request(
            'http://127.0.0.1:8780/v1/participants/join/challenge',
            data=payload,
            headers={'Content-Type':'application/json'},
            method='POST',
        )
        with urllib.request.urlopen(req,timeout=10) as resp:
            verified=json.loads(resp.read().decode('utf-8'))
        if verified.get('ok') is not True:
            raise RuntimeError('participant_challenge_verification_failed')
        state['status']='challenge_verified'
        state['challenge_verified_at']=verified.get('verified_at')
        state['challenge_response_digest']=verified.get('response_digest')
        tmp=state_path.with_suffix(state_path.suffix+'.tmp')
        tmp.write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        tmp.chmod(0o600); tmp.replace(state_path); state_path.chmod(0o600)
        print('participant_challenge_request_id='+str(state['request_id']))
        print('participant_challenge_verified=PASS')
    else:
        print('gemini_web_roundtrip_marker=AGENTOS_GEMINI_BRIDGE_OK')

    print('gemini_web_roundtrip_acceptance=PASS')
PY
