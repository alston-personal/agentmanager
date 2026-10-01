#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -un)" != "ubuntu" ]; then
  echo "threads_web_dm_login_probe=WRONG_USER" >&2
  exit 2
fi

ROOT="$HOME/.local/share/agentos/gui-worker"
NODE="$(find "$ROOT/venv/lib" -type f -path '*/playwright/driver/node' -print -quit)"
test -n "$NODE"
test -x "$NODE"

"$NODE" <<'JS'
const fs = require('fs');
const path = require('path');

const BASE = 'http://127.0.0.1:9222';
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

async function fetchJson(url, options={}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 5000);
  try {
    const res = await fetch(url, {...options, signal: controller.signal});
    if (!res.ok) throw new Error('cdp_http_'+res.status);
    return await res.json();
  } finally {
    clearTimeout(timer);
  }
}

async function evaluate(wsUrl, expression) {
  if (typeof WebSocket !== 'function') throw new Error('node_websocket_unavailable');
  return await new Promise((resolve, reject) => {
    const ws = new WebSocket(wsUrl);
    ws.binaryType = 'arraybuffer';
    const timer = setTimeout(() => {
      try { ws.close(); } catch {}
      reject(new Error('cdp_runtime_timeout'));
    }, 7000);
    const finish = (fn, value) => {
      clearTimeout(timer);
      try { ws.close(); } catch {}
      fn(value);
    };
    ws.addEventListener('open', () => {
      ws.send(JSON.stringify({
        id: 1,
        method: 'Runtime.evaluate',
        params: {
          expression,
          returnByValue: true,
          awaitPromise: true,
        },
      }));
    });
    ws.addEventListener('message', async event => {
      let raw = event.data;
      try {
        if (typeof raw !== 'string') {
          if (raw instanceof ArrayBuffer) {
            raw = Buffer.from(raw).toString('utf8');
          } else if (ArrayBuffer.isView(raw)) {
            raw = Buffer.from(raw.buffer, raw.byteOffset, raw.byteLength).toString('utf8');
          } else if (raw && typeof raw.text === 'function') {
            raw = await raw.text();
          } else {
            raw = String(raw);
          }
        }
        const doc = JSON.parse(raw);
        if (doc.id !== 1) return;
        if (doc.error) return finish(reject, new Error('cdp_runtime_error'));
        const value = doc?.result?.result?.value;
        finish(resolve, value);
      } catch {
        return;
      }
    });
    ws.addEventListener('error', () => finish(reject, new Error('cdp_websocket_error')));
  });
}

(async () => {
  let targetId = '';
  try {
    const meta = await fetchJson(BASE+'/json/version');
    if (!meta.webSocketDebuggerUrl) throw new Error('cdp_unavailable');

    const target = await fetchJson(
      BASE+'/json/new?'+encodeURIComponent('https://www.threads.com/messages'),
      {method:'PUT'},
    );
    targetId = String(target.id || '');
    if (!targetId || !target.webSocketDebuggerUrl) throw new Error('cdp_target_create_failed');

    await sleep(3000);
    const items = await fetchJson(BASE+'/json/list');
    const current = items.find(x => String(x.id || '') === targetId) || target;
    const wsUrl = String(current.webSocketDebuggerUrl || target.webSocketDebuggerUrl || '');
    if (!wsUrl) throw new Error('cdp_target_ws_missing');

    const finalUrl = String(await evaluate(wsUrl, 'location.href') || '');
    const lowUrl = finalUrl.toLowerCase();

    let state = 'UNKNOWN';
    let resumeCandidate = false;
    let mioHint = false;

    // Never read the body of an authenticated messages page: it may contain
    // private conversation snippets. Inspect DOM text only after a login redirect.
    if (lowUrl.includes('/messages') && lowUrl.includes('threads.com')) {
      state = 'AUTHENTICATED';
    } else {
      let body = '';
      for (let i=0; i<4; i++) {
        body = String(await evaluate(
          wsUrl,
          "(document.body ? document.body.innerText : '').slice(0,12000)",
        ) || '');
        if (body.trim()) break;
        await sleep(750);
      }
      const low = (finalUrl+'\n'+body).toLowerCase();
      if (lowUrl.includes('/login') || low.includes('accountscenter') || low.includes('log in') || body.includes('登入')) {
        state = 'LOGIN_REQUIRED';
      } else if (low.includes('try again later') || low.includes('restrict certain activity') || body.includes('稍後再試')) {
        state = 'BLOCKED';
      }

      if (state === 'LOGIN_REQUIRED') {
        const compact = low.replace(/\s+/g,' ').trim();
        resumeCandidate = [
          'continue with instagram',
          'continue as',
          '繼續使用 instagram',
          '使用 instagram 繼續',
          '繼續以',
        ].some(x => compact.includes(x));
        mioHint = compact.includes('mio.milkcat') || compact.includes('@mio.milkcat');
      }
    }

    const root = '/home/ubuntu/agent-data/runtime/social/threads-web-dm';
    fs.mkdirSync(root,{recursive:true,mode:0o700});
    try { fs.chmodSync(root,0o700); } catch {}
    const out = path.join(root,'login-probe.json');
    fs.writeFileSync(out,JSON.stringify({
      schema:'agentos.threads-web-dm-login-probe/v4',
      mode:'oracle_gui_worker',
      transport:'cdp_node_websocket',
      session_state:state,
      resume_candidate:resumeCandidate,
      mio_account_hint:mioHint,
    },null,2)+'\n',{mode:0o600});
    fs.chmodSync(out,0o600);

    console.log('threads_web_dm_login_probe=PASS');
    console.log('threads_web_dm_login_mode=oracle_gui_worker');
    console.log('threads_web_dm_login_transport=cdp_node_websocket');
    console.log('threads_web_dm_login_session_state='+state);
    console.log('threads_web_dm_login_resume_candidate='+String(resumeCandidate));
    console.log('threads_web_dm_login_mio_account_hint='+String(mioHint));
  } finally {
    if (targetId) {
      try {
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), 3000);
        await fetch(BASE+'/json/close/'+encodeURIComponent(targetId),{signal:controller.signal});
        clearTimeout(timer);
      } catch {}
    }
  }
})().catch(err => {
  console.error('threads_web_dm_login_probe=ERROR');
  console.error('threads_web_dm_login_error_type='+String(err?.message || 'unknown').replace(/[^A-Za-z0-9_.:-]/g,'_').slice(0,100));
  process.exit(1);
});
JS
