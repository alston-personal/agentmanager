#!/usr/bin/env python3
from __future__ import annotations
import json, os, time
from agent_core.realm_fabric import RealmFabricStore

def main() -> int:
    decision_path=os.environ['MIO_DM_DECISION_PATH']
    target=os.environ.get('MIO_DM_TARGET','')
    if target!='0__0.ayoub':
        raise SystemExit('unexpected DM target')
    d=json.load(open(decision_path,encoding='utf-8'))
    if d.get('decision')!='reply':
        raise SystemExit('decision is not reply')
    text=str(d.get('text') or '').strip()
    if not text or len(text)>500:
        raise SystemExit('invalid DM reply text')

    js_click=f"""(()=>{{const els=[...document.querySelectorAll('a,button,div[role=button]')];const e=els.find(x=>(x.innerText||'').includes({json.dumps(target)}));if(!e)return 'NOT_FOUND';e.click();return 'CLICKED';}})()"""
    js_send=f"""(()=>{{const box=document.querySelector('textarea,[contenteditable="true"]');if(!box)return 'NO_BOX';box.focus();if(box.tagName==='TEXTAREA'){{const s=Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value').set;s.call(box,{json.dumps(text)});box.dispatchEvent(new Event('input',{{bubbles:true}}));}}else{{document.execCommand('selectAll',false,null);document.execCommand('insertText',false,{json.dumps(text)});box.dispatchEvent(new InputEvent('input',{{bubbles:true,inputType:'insertText',data:{json.dumps(text)}}}));}}const buttons=[...document.querySelectorAll('button,[role=button]')];const send=buttons.find(x=>/^(Send|傳送)$/i.test((x.innerText||x.getAttribute('aria-label')||'').trim()));if(send){{send.click();return 'SENT_BUTTON';}}box.dispatchEvent(new KeyboardEvent('keydown',{{key:'Enter',code:'Enter',keyCode:13,which:13,bubbles:true}}));box.dispatchEvent(new KeyboardEvent('keypress',{{key:'Enter',code:'Enter',keyCode:13,which:13,bubbles:true}}));box.dispatchEvent(new KeyboardEvent('keyup',{{key:'Enter',code:'Enter',keyCode:13,which:13,bubbles:true}}));return 'SENT_ENTER';}})()"""
    js_verify=f"""(()=>{{const t=(document.querySelector('main')?.innerText||document.body.innerText||'');return t.includes({json.dumps(text)})?'FOUND':'MISSING';}})()"""
    osa='\n'.join([
        'tell application "Google Chrome"',
        'activate',
        'set t to active tab of front window',
        'set u to URL of t',
        'if u does not start with "https://www.threads.com/messages" and u does not start with "https://threads.com/messages" then set URL of t to "https://www.threads.com/messages"',
        'delay 2',
        'set r1 to execute t javascript '+json.dumps(js_click),
        'delay 2',
        'set r2 to execute t javascript '+json.dumps(js_send),
        'delay 3',
        'set r3 to execute t javascript '+json.dumps(js_verify),
        'return (r1 & linefeed & r2 & linefeed & r3)',
        'end tell',
    ])
    code="import subprocess; s="+repr(osa)+"; p=subprocess.run(['/usr/bin/osascript','-e',s],text=True,capture_output=True,timeout=30); print(p.stdout,end=''); raise SystemExit(p.returncode)"
    tid='mio-dm-send-'+str(int(time.time()))
    store=RealmFabricStore()
    store.queue_task('mbpr',{'schema':'agentos.node-task/v0.1','task_id':tid,'action':'shell.exec','executable':'python3','argv':['-c',code],'cwd':'/Users/tengweihuang/AgentOS','timeout_seconds':40,'cognition_ids_used':[]})
    for _ in range(50):
        r=store.get_receipt(tid)
        if r:
            out=str(r.get('stdout') or '')
            if r.get('ok') is not True or int(r.get('returncode') or 0)!=0:
                raise SystemExit('mio_dm_send=ERROR')
            lines=[x.strip() for x in out.splitlines() if x.strip()]
            if 'FOUND' not in lines:
                raise SystemExit('mio_dm_send=UNVERIFIED')
            print('mio_dm_send=PASS')
            print('mio_dm_send_target='+target)
            print('mio_dm_send_readback=PASS')
            print('mio_dm_send_receipt='+tid)
            return 0
        time.sleep(2)
    raise SystemExit('mio_dm_send=TIMEOUT')

if __name__=='__main__':
    raise SystemExit(main())
