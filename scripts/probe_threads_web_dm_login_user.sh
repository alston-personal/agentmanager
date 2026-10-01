#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -un)" != "ubuntu" ]; then
  echo "threads_web_dm_login_probe=WRONG_USER" >&2
  exit 2
fi

python3 - <<'PY'
import base64
import hashlib
import json
import os
import socket
import struct
import time
import urllib.parse
import urllib.request
from pathlib import Path

BASE='http://127.0.0.1:9222'

def http_json(url, *, method='GET'):
    req=urllib.request.Request(url,method=method)
    with urllib.request.urlopen(req,timeout=5) as r:
        return json.load(r)

def recv_exact(sock, n):
    out=bytearray()
    while len(out)<n:
        chunk=sock.recv(n-len(out))
        if not chunk:
            raise RuntimeError('cdp_ws_closed')
        out.extend(chunk)
    return bytes(out)

def send_frame(sock, payload, opcode=1):
    data=payload if isinstance(payload,bytes) else payload.encode('utf-8')
    mask=os.urandom(4)
    n=len(data)
    if n<126:
        header=bytes([0x80|opcode,0x80|n])
    elif n<65536:
        header=bytes([0x80|opcode,0x80|126])+struct.pack('!H',n)
    else:
        header=bytes([0x80|opcode,0x80|127])+struct.pack('!Q',n)
    masked=bytes(b ^ mask[i%4] for i,b in enumerate(data))
    sock.sendall(header+mask+masked)

def recv_text(sock):
    fragments=[]
    while True:
        b1,b2=recv_exact(sock,2)
        fin=bool(b1&0x80)
        opcode=b1&0x0f
        masked=bool(b2&0x80)
        n=b2&0x7f
        if n==126:
            n=struct.unpack('!H',recv_exact(sock,2))[0]
        elif n==127:
            n=struct.unpack('!Q',recv_exact(sock,8))[0]
        mask=recv_exact(sock,4) if masked else None
        payload=recv_exact(sock,n)
        if mask:
            payload=bytes(b ^ mask[i%4] for i,b in enumerate(payload))
        if opcode==0x9:
            send_frame(sock,payload,opcode=0xA)
            continue
        if opcode==0x8:
            raise RuntimeError('cdp_ws_close_frame')
        if opcode in (0x1,0x0):
            fragments.append(payload)
            if fin:
                return b''.join(fragments).decode('utf-8','replace')

def cdp_eval(ws_url, expression, request_id=1):
    parsed=urllib.parse.urlparse(ws_url)
    if parsed.scheme!='ws' or not parsed.hostname:
        raise RuntimeError('invalid_cdp_ws_url')
    port=parsed.port or 80
    sock=socket.create_connection((parsed.hostname,port),timeout=5)
    sock.settimeout(5)
    try:
        key=base64.b64encode(os.urandom(16)).decode()
        path=parsed.path or '/'
        if parsed.query:
            path+='?'+parsed.query
        req=(
            f'GET {path} HTTP/1.1\r\n'
            f'Host: {parsed.hostname}:{port}\r\n'
            'Upgrade: websocket\r\n'
            'Connection: Upgrade\r\n'
            f'Sec-WebSocket-Key: {key}\r\n'
            'Sec-WebSocket-Version: 13\r\n\r\n'
        ).encode()
        sock.sendall(req)
        headers=bytearray()
        while b'\r\n\r\n' not in headers and len(headers)<16384:
            headers.extend(recv_exact(sock,1))
        first=headers.split(b'\r\n',1)[0]
        if b' 101 ' not in first:
            raise RuntimeError('cdp_ws_upgrade_failed')
        msg={
            'id':request_id,
            'method':'Runtime.evaluate',
            'params':{
                'expression':expression,
                'returnByValue':True,
                'awaitPromise':True,
            },
        }
        send_frame(sock,json.dumps(msg,separators=(',',':')))
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            doc=json.loads(recv_text(sock))
            if doc.get('id')!=request_id:
                continue
            if 'error' in doc:
                raise RuntimeError('cdp_runtime_error')
            return (((doc.get('result') or {}).get('result') or {}).get('value'))
        raise TimeoutError('cdp_runtime_timeout')
    finally:
        sock.close()

meta=http_json(BASE+'/json/version')
assert meta.get('webSocketDebuggerUrl')

target=None
target_id=None
try:
    url='https://www.threads.com/messages'
    target=http_json(BASE+'/json/new?'+urllib.parse.quote(url,safe=''),method='PUT')
    target_id=str(target.get('id') or '')
    assert target_id and target.get('webSocketDebuggerUrl')

    # Let redirects settle. The target stays isolated from the existing login tab
    # but shares the persistent browser profile/session.
    time.sleep(3)
    items=http_json(BASE+'/json/list')
    current=next((x for x in items if str(x.get('id') or '')==target_id),target)
    ws=str(current.get('webSocketDebuggerUrl') or target.get('webSocketDebuggerUrl') or '')
    final_url=str(cdp_eval(ws,'location.href') or '')

    state='UNKNOWN'
    resume_candidate=False
    mio_hint=False
    low_url=final_url.lower()

    # Avoid reading message-page body text when authenticated: it may contain
    # private conversation snippets. DOM text is inspected only on login pages,
    # and only booleans leave Oracle.
    if '/messages' in low_url and 'threads.com' in low_url:
        state='AUTHENTICATED'
    else:
        body=''
        for _ in range(4):
            value=cdp_eval(
                ws,
                "(document.body ? document.body.innerText : '').slice(0,12000)",
                request_id=2,
            )
            body=str(value or '')
            if body.strip():
                break
            time.sleep(0.75)
        low=(final_url+'\n'+body).lower()
        if '/login' in low_url or 'accountscenter' in low or 'log in' in low or '登入' in body:
            state='LOGIN_REQUIRED'
        elif 'try again later' in low or 'restrict certain activity' in low or '稍後再試' in body:
            state='BLOCKED'

        if state=='LOGIN_REQUIRED':
            compact=' '.join(low.split())
            resume_candidate=any(x in compact for x in (
                'continue with instagram',
                'continue as',
                '繼續使用 instagram',
                '使用 instagram 繼續',
                '繼續以',
            ))
            mio_hint=('mio.milkcat' in compact or '@mio.milkcat' in compact)

    root=Path('/home/ubuntu/agent-data/runtime/social/threads-web-dm')
    root.mkdir(parents=True,exist_ok=True)
    os.chmod(root,0o700)
    out=root/'login-probe.json'
    out.write_text(json.dumps({
        'schema':'agentos.threads-web-dm-login-probe/v3',
        'mode':'oracle_gui_worker',
        'transport':'cdp_websocket',
        'session_state':state,
        'resume_candidate':resume_candidate,
        'mio_account_hint':mio_hint,
    },sort_keys=True,indent=2)+'\n',encoding='utf-8')
    os.chmod(out,0o600)

    print('threads_web_dm_login_probe=PASS')
    print('threads_web_dm_login_mode=oracle_gui_worker')
    print('threads_web_dm_login_transport=cdp_websocket')
    print('threads_web_dm_login_session_state='+state)
    print('threads_web_dm_login_resume_candidate='+str(resume_candidate).lower())
    print('threads_web_dm_login_mio_account_hint='+str(mio_hint).lower())
finally:
    if target_id:
        try:
            urllib.request.urlopen(BASE+'/json/close/'+urllib.parse.quote(target_id,safe=''),timeout=3).read()
        except Exception:
            pass
PY
