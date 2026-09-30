#!/usr/bin/env python3
from __future__ import annotations

import base64, hashlib, json, os, socket, struct, time, urllib.request
from urllib.parse import urlsplit, quote

def _json_get(url: str):
    with urllib.request.urlopen(url, timeout=5) as r:
        return json.load(r)

class _WS:
    def __init__(self, url: str):
        u=urlsplit(url)
        if u.scheme!='ws': raise RuntimeError('only ws:// supported')
        self.sock=socket.create_connection((u.hostname,u.port or 80),timeout=8)
        key=base64.b64encode(os.urandom(16)).decode()
        path=u.path+(('?'+u.query) if u.query else '')
        req=(f'GET {path} HTTP/1.1\r\nHost: {u.hostname}:{u.port or 80}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n')
        self.sock.sendall(req.encode('ascii'))
        head=b''
        while b'\r\n\r\n' not in head and len(head)<65536:
            ch=self.sock.recv(4096)
            if not ch: break
            head+=ch
        if not head.startswith(b'HTTP/1.1 101'): raise RuntimeError('cdp websocket handshake failed')
    def _read_exact(self,n):
        out=b''
        while len(out)<n:
            ch=self.sock.recv(n-len(out))
            if not ch: raise RuntimeError('cdp websocket closed')
            out+=ch
        return out
    def send_text(self,text):
        p=text.encode(); m=os.urandom(4); n=len(p); h=bytearray([0x81])
        if n<126: h.append(0x80|n)
        elif n<65536: h.append(0x80|126); h.extend(struct.pack('!H',n))
        else: h.append(0x80|127); h.extend(struct.pack('!Q',n))
        self.sock.sendall(bytes(h)+m+bytes(b^m[i%4] for i,b in enumerate(p)))
    def recv_text(self):
        while True:
            b1,b2=self._read_exact(2); op=b1&0x0F; n=b2&0x7F
            if n==126: n=struct.unpack('!H',self._read_exact(2))[0]
            elif n==127: n=struct.unpack('!Q',self._read_exact(8))[0]
            mask=self._read_exact(4) if (b2&0x80) else None
            p=self._read_exact(n)
            if mask: p=bytes(b^mask[i%4] for i,b in enumerate(p))
            if op==1: return p.decode('utf-8','replace')
            if op==8: raise RuntimeError('closed')
    def close(self):
        try:self.sock.close()
        except:pass

def _eval(ws,expr,cid):
    ws.send_text(json.dumps({'id':cid,'method':'Runtime.evaluate','params':{'expression':expr,'returnByValue':True,'awaitPromise':True}},separators=(',',':')))
    while True:
        m=json.loads(ws.recv_text())
        if m.get('id')!=cid: continue
        if 'error' in m: raise RuntimeError('Runtime.evaluate failed')
        return (((m.get('result') or {}).get('result') or {}).get('value'))

def _threads_tab():
    tabs=_json_get('http://127.0.0.1:9222/json/list')
    c=[t for t in tabs if 'threads.com' in str(t.get('url') or '') and t.get('webSocketDebuggerUrl')]
    if not c: raise RuntimeError('no Threads tab')
    # Prefer an authenticated messages tab if present.
    c.sort(key=lambda t: 0 if '/messages' in str(t.get('url') or '') else 1)
    return c[0]

def main():
    query=os.environ.get('THREADS_SEARCH_QUERY','貓').strip()
    tab=_threads_tab()
    ws=_WS(str(tab['webSocketDebuggerUrl']))
    try:
        search_url='https://www.threads.com/search?q='+quote(query)+'&serp_type=recent'
        _eval(ws,'location.href='+json.dumps(search_url),1)
        time.sleep(8)
        expr=r"""(()=>{
          const all=[...document.querySelectorAll('a[href*="/post/"]')];
          const out=[]; const seen=new Set();
          for(const a of all){
            let href=a.href.replace(/\/media$/,'');
            if(!href.includes('/post/')||seen.has(href)) continue;
            seen.add(href);
            let node=a;
            let txt='';
            for(let i=0;i<9&&node;i++,node=node.parentElement){
              const s=(node.innerText||'').trim();
              if(s.length>txt.length) txt=s;
              if(s.length>=30 && /\n/.test(s)) break;
            }
            out.push({href,text:txt.slice(0,700)});
            if(out.length>=15) break;
          }
          return {url:location.href,title:document.title,body:(document.body?.innerText||'').slice(0,1800),rows:out};
        })()"""
        val=_eval(ws,expr,2) or {}
        print(json.dumps({'schema':'agentos.threads-web-search/v1','query':query,'url':val.get('url'),'rows':val.get('rows') or [],'body_sample':str(val.get('body') or '')[:1000]},ensure_ascii=False))
    finally:
        ws.close()

if __name__=='__main__':
    main()
