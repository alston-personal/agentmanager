// Bounded, read-only existing-tab Threads account evidence for issue #1735.
// No tabs created, navigated, closed, or mutated. No DOM text, cookies or messages.
const PORTS = [{port: 9223, expected: 'oursong_alstonhuang'},
               {port: 9224, expected: 'mio.milkcat'}];
const HOSTS = new Set(['threads.com', 'www.threads.com']);

async function json(url) {
  const response = await fetch(url, {signal: AbortSignal.timeout(3500)});
  if (!response.ok) throw Error('CDP_HTTP_ERROR');
  return response.json();
}
function accountEvidence(hrefs, expected) {
  const candidates = new Set();
  for (const href of Array.isArray(hrefs) ? hrefs : []) {
    try {
      const u = new URL(String(href), 'https://www.threads.com');
      if (!HOSTS.has(u.hostname.toLowerCase())) continue;
      const match = new RegExp('^/@([a-z0-9_.]+)(?:/|$)', 'i').exec(u.pathname);
      if (match) candidates.add(match[1].toLowerCase());
    } catch {}
  }
  if (candidates.size > 1) return 'AMBIGUOUS';
  if (candidates.size === 0) return 'UNKNOWN';
  return candidates.has(expected.toLowerCase()) ? 'EXPECTED' : 'MISMATCH';
}
async function evaluateExistingTab(wsUrl) {
  const expression = `(() => {
    const selectors = [
      'a[href][aria-label*="profile" i]',
      'a[href][title*="profile" i]',
      'a[href][aria-label*="個人檔案"]',
      'a[href][title*="個人檔案"]',
      '[role="navigation"] a[href^="/@"]',
      'nav a[href^="/@"]'
    ].join(',');
    return Array.from(document.querySelectorAll(selectors))
      .slice(0, 20).map(a => a.getAttribute('href') || '');
  })()`;
  return new Promise((resolve, reject) => {
    const socket = new WebSocket(wsUrl);
    const timeout = setTimeout(() => { socket.close(); reject(Error('CDP_TIMEOUT')); }, 6000);
    const finish = (cb, value) => { clearTimeout(timeout); socket.close(); cb(value); };
    socket.addEventListener('open', () => socket.send(JSON.stringify({
      id: 1, method: 'Runtime.evaluate',
      params: {expression, returnByValue: true, awaitPromise: false}
    })));
    socket.addEventListener('message', event => {
      try {
        const response = JSON.parse(String(event.data));
        if (response.id !== 1) return;
        if (response.error || response.result?.exceptionDetails)
          return finish(reject, Error('CDP_EVALUATION_ERROR'));
        finish(resolve, response.result?.result?.value);
      } catch { finish(reject, Error('CDP_RESPONSE_INVALID')); }
    });
    socket.addEventListener('error', () => finish(reject, Error('CDP_WEBSOCKET_ERROR')));
  });
}
async function inspect({port, expected}) {
  const summary = {port, cdp_state: 'UNAVAILABLE', account_state: 'UNKNOWN',
                   examined_threads_pages: 0, page_targets: 0,
                   threads_page_targets: 0, threads_ws_targets: 0,
                   classification: 'CDP_UNAVAILABLE', account_identity_verified: false};
  try {
    const tabs = await json('http://127.0.0.1:' + port + '/json/list');
    summary.cdp_state = 'READY';
    summary.classification = 'NO_THREADS_TAB';
    if (!Array.isArray(tabs)) return summary;
    // Count all page metadata first. Bound only active WebSocket evaluations.
    const pages = tabs.filter(tab => tab && tab.type === 'page');
    summary.page_targets = pages.length;
    const threads = pages.filter(tab => {
      try { return HOSTS.has(new URL(tab.url).hostname.toLowerCase()); }
      catch { return false; }
    });
    summary.threads_page_targets = threads.length;
    const states = [];
    for (const tab of threads.slice(0, 3)) {
      if (!tab.webSocketDebuggerUrl) { summary.classification = 'THREADS_WS_MISSING'; continue; }
      summary.threads_ws_targets += 1;
      summary.examined_threads_pages += 1;
      try { states.push(accountEvidence(
        await evaluateExistingTab(tab.webSocketDebuggerUrl), expected));
      } catch { states.push('UNKNOWN'); }
    }
    if (summary.threads_ws_targets) summary.classification = 'EVALUATED_EXISTING_TAB';
    const definite = states.filter(s => s === 'EXPECTED' || s === 'MISMATCH');
    if (states.includes('AMBIGUOUS') || new Set(definite).size > 1)
      summary.account_state = 'AMBIGUOUS';
    else if (definite.length > 0 && states.every(s => s === definite[0]))
      summary.account_state = definite[0];
    else summary.account_state = 'UNKNOWN';
  } catch {}
  return summary;
}
(async () => {
  const records = [];
  for (const entry of PORTS) records.push(await inspect(entry));
  console.log(JSON.stringify({schema:'agentos.threads-existing-tab-readback/v1',
    read_only:true, account_identity_verified:false, records}));
})().catch(() => { console.log(JSON.stringify({
  schema:'agentos.threads-existing-tab-readback/v1', read_only:true,
  account_identity_verified:false, classification:'ERROR'})); });
