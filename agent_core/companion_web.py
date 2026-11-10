"""AgentOS Mobile Companion & Web Console Interface.

Provides a clean, touch-friendly, mobile-first Web Console for AgentOS.
Allows remote operators (via phone, tablet, or browser) to:
1. Inspect and resolve interactive Approval Cards (OptionCards) with one tap.
2. Approve Device / Node Enrollment Codes (e.g. DBG9-9H4R) directly on screen.
3. Monitor Live Realm Node Map (online/offline nodes, OS, agents, heartbeats).
4. Monitor live system health, task queues, and all 21 active role workers.
5. Dispatch new tasks directly to Oracle local executors without opening the IDE.
"""
from __future__ import annotations

import json
from typing import Any

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
  <title>AgentOS Web Console & Companion</title>
  <meta name="robots" content="noindex, nofollow">
  <style>
    :root {
      --bg: #090d16;
      --card-bg: #131b2e;
      --card-border: #1e293b;
      --text: #f1f5f9;
      --muted: #94a3b8;
      --primary: #3b82f6;
      --success: #10b981;
      --danger: #ef4444;
      --warning: #f59e0b;
      --font-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background: var(--bg);
      color: var(--text);
      font-family: var(--font-sans);
      padding: 16px;
      line-height: 1.5;
      -webkit-font-smoothing: antialiased;
    }
    .container { max-width: 640px; margin: 0 auto; }
    header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding-bottom: 16px;
      border-bottom: 1px solid var(--card-border);
      margin-bottom: 20px;
    }
    .brand { font-size: 1.25rem; font-weight: 700; color: #fff; display: flex; align-items: center; gap: 8px; }
    .badge-pulse {
      display: inline-block; width: 10px; height: 10px; border-radius: 50%;
      background: var(--success); box-shadow: 0 0 10px var(--success);
    }
    .host-tag { font-size: 0.75rem; color: var(--muted); background: #1e293b; padding: 4px 8px; border-radius: 4px; }
    h2 { font-size: 1.05rem; font-weight: 600; margin-bottom: 12px; color: #e2e8f0; display: flex; align-items: center; justify-content: space-between; }
    .section { margin-bottom: 24px; }
    .card {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 12px;
      padding: 16px;
      margin-bottom: 12px;
      box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.3);
    }
    .card.pending-approval {
      border-left: 4px solid var(--warning);
    }
    .card-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 8px; }
    .card-title { font-weight: 600; font-size: 1rem; color: #fff; }
    .card-meta { font-size: 0.8rem; color: var(--muted); margin-bottom: 10px; }
    .card-payload {
      background: #0b1120;
      border: 1px solid #1e293b;
      border-radius: 6px;
      padding: 10px;
      font-size: 0.8rem;
      font-family: monospace;
      color: #38bdf8;
      overflow-x: auto;
      margin-bottom: 12px;
      max-height: 120px;
    }
    .card-actions { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
    button {
      padding: 10px 14px;
      font-size: 0.95rem;
      font-weight: 600;
      border-radius: 8px;
      border: none;
      cursor: pointer;
      transition: all 0.2s ease;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 6px;
    }
    button:active { transform: scale(0.97); }
    .btn-approve { background: #059669; color: #fff; }
    .btn-approve:hover { background: #10b981; }
    .btn-reject { background: #dc2626; color: #fff; }
    .btn-reject:hover { background: #ef4444; }
    .btn-primary { background: var(--primary); color: #fff; width: 100%; }
    .btn-primary:hover { background: #2563eb; }
    .empty-state {
      background: var(--card-bg);
      border: 1px dashed var(--card-border);
      border-radius: 12px;
      padding: 20px;
      text-align: center;
      color: var(--muted);
      font-size: 0.85rem;
    }
    .form-group { margin-bottom: 12px; }
    label { display: block; font-size: 0.8rem; font-weight: 500; color: var(--muted); margin-bottom: 4px; }
    input, select, textarea {
      width: 100%;
      background: #0b1120;
      border: 1px solid var(--card-border);
      border-radius: 8px;
      padding: 10px 12px;
      color: #fff;
      font-size: 0.9rem;
      font-family: inherit;
    }
    input:focus, select:focus, textarea:focus { outline: none; border-color: var(--primary); }
    textarea { resize: vertical; min-height: 60px; }
    .roles-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(110px, 1fr));
      gap: 8px;
    }
    .role-chip {
      background: #0f172a;
      border: 1px solid #1e293b;
      border-radius: 6px;
      padding: 6px 8px;
      font-size: 0.75rem;
      text-align: center;
      color: #cbd5e1;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 4px;
    }
    .role-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--success); }
    .toast {
      position: fixed;
      bottom: 20px;
      left: 50%;
      transform: translateX(-50%);
      background: #1e293b;
      color: #fff;
      padding: 10px 20px;
      border-radius: 20px;
      font-size: 0.85rem;
      box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.5);
      display: none;
      z-index: 100;
    }
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div class="brand">
        <span class="badge-pulse"></span>
        AgentOS Console
      </div>
      <div class="host-tag">agentos.milkcat.org | Oracle Core</div>
    </header>

    <!-- SECTION: NODE JOIN APPROVAL -->
    <div class="section">
      <h2>Approve Node Join (節點設備配對審批)</h2>
      <div class="card">
        <div class="form-group">
          <label>Device User Code (輸入終端機顯示的 8 碼配對碼)</label>
          <div style="display:flex; gap:8px;">
            <input type="text" id="node-join-code" placeholder="e.g. DBG9-9H4R" style="text-transform:uppercase; font-size:1.1rem; letter-spacing:2px; font-weight:700;">
            <button class="btn-approve" style="white-space:nowrap; padding:10px 16px;" id="btn-approve-node" onclick="approveNodeCode()">
              🛡️ Approve
            </button>
          </div>
        </div>
        <div id="node-approve-result" style="display:none; margin-top:8px;"></div>
      </div>
    </div>

    <!-- SECTION: REALM NODE MAP -->
    <div class="section">
      <h2>
        <span>Realm Node Map (節點拓撲圖)</span>
        <span id="node-online-count" style="font-size:0.8rem; color:var(--success);">0 online</span>
      </h2>
      <div id="nodes-container">
        <div class="empty-state">Loading node topology...</div>
      </div>
    </div>

    <!-- SECTION: APPROVAL CARDS -->
    <div class="section">
      <h2>
        <span>Governance Approvals (OptionCard)</span>
        <span id="approval-count" style="font-size:0.8rem; color:var(--warning)">0</span>
      </h2>
      <div id="approvals-container">
        <div class="empty-state">Checking pending approvals...</div>
      </div>
    </div>

    <!-- SECTION: TASK DISPATCHER -->
    <div class="section">
      <h2>Dispatch Task to Oracle Local</h2>
      <div class="card">
        <div class="form-group">
          <label>Target Capability / Role</label>
          <select id="task-capability">
            <option value="system.paw">system.paw (Engineering Execution)</option>
            <option value="system.claw">system.claw (Review & Acceptance)</option>
            <option value="system.cartographer">system.cartographer (World Model & Resources)</option>
            <option value="system.atlas">system.atlas (Search & Indexing)</option>
            <option value="system.zeus_writer">system.zeus_writer (Creative Publishing)</option>
            <option value="system.iris_dns">system.iris_dns (Network & DNS Ingress)</option>
            <option value="core.supervisor">core.supervisor (Runtime Orchestration)</option>
          </select>
        </div>
        <div class="form-group">
          <label>Task Goal</label>
          <textarea id="task-goal" placeholder="e.g. Audit world model resources, check queue status, or run verification cycle..."></textarea>
        </div>
        <button class="btn-primary" id="btn-dispatch" onclick="dispatchTask()">
          🚀 Submit Task to Local Executor
        </button>
        <div id="dispatch-result" style="margin-top:10px; display:none;"></div>
      </div>
    </div>

    <!-- SECTION: LIVE ROLES -->
    <div class="section">
      <h2>Active Roles (21 / 21 Live Runtime)</h2>
      <div class="roles-grid" id="roles-container">
        <div class="role-chip"><span class="role-dot"></span>Paw</div>
        <div class="role-chip"><span class="role-dot"></span>Claw</div>
        <div class="role-chip"><span class="role-dot"></span>Supervisor</div>
        <div class="role-chip"><span class="role-dot"></span>Cartographer</div>
        <div class="role-chip"><span class="role-dot"></span>Mnemosyne</div>
        <div class="role-chip"><span class="role-dot"></span>Eunomia</div>
        <div class="role-chip"><span class="role-dot"></span>Zeus Writer</div>
        <div class="role-chip"><span class="role-dot"></span>Venus</div>
        <div class="role-chip"><span class="role-dot"></span>YouTube AI</div>
        <div class="role-chip"><span class="role-dot"></span>Weaver</div>
        <div class="role-chip"><span class="role-dot"></span>Whisperer</div>
        <div class="role-chip"><span class="role-dot"></span>Spec Steward</div>
        <div class="role-chip"><span class="role-dot"></span>Constitution</div>
        <div class="role-chip"><span class="role-dot"></span>Iris DNS</div>
        <div class="role-chip"><span class="role-dot"></span>Arbiter</div>
        <div class="role-chip"><span class="role-dot"></span>Chronicler</div>
        <div class="role-chip"><span class="role-dot"></span>Thales</div>
        <div class="role-chip"><span class="role-dot"></span>Atlas</div>
        <div class="role-chip"><span class="role-dot"></span>Atlast</div>
        <div class="role-chip"><span class="role-dot"></span>Growth</div>
        <div class="role-chip"><span class="role-dot"></span>Security</div>
      </div>
    </div>

    <!-- SECTION: HISTORY -->
    <div class="section">
      <h2>Recent Approvals History</h2>
      <div id="history-container">
        <div class="empty-state">Loading history...</div>
      </div>
    </div>
  </div>

  <div id="toast" class="toast"></div>

  <script>
    const API_BASE = window.location.pathname.startsWith('/agentos') ? '/agentos' : '';
    // Credentials are NEVER embedded in served HTML. The operator signs in once
    // on each device; the token stays in this browser's localStorage only.
    const TOKEN_KEY = 'agentos_operator_token';
    function getToken() {
      let t = localStorage.getItem(TOKEN_KEY) || '';
      if (!t) {
        t = (window.prompt('AgentOS operator token (stored only on this device):') || '').trim();
        if (t) localStorage.setItem(TOKEN_KEY, t);
      }
      return t;
    }
    function signOut() { localStorage.removeItem(TOKEN_KEY); location.reload(); }

    function getHeaders() {
      const h = { 'Content-Type': 'application/json' };
      const t = getToken();
      if (t) h['Authorization'] = 'Bearer ' + t;
      return h;
    }
    const _origFetch = window.fetch.bind(window);
    window.fetch = async (...args) => {
      const r = await _origFetch(...args);
      if (r.status === 401 || r.status === 403) {
        localStorage.removeItem(TOKEN_KEY);
      }
      return r;
    };

    function showToast(msg) {
      const toast = document.getElementById('toast');
      toast.innerText = msg;
      toast.style.display = 'block';
      setTimeout(() => { toast.style.display = 'none'; }, 3000);
    }

    async function loadApprovals() {
      try {
        const resp = await fetch(API_BASE + '/v1/approvals', { headers: getHeaders() });
        if (!resp.ok) return;
        const data = await resp.json();

        document.getElementById('approval-count').innerText = data.pending_count || 0;
        const container = document.getElementById('approvals-container');

        if (!data.cards || data.cards.length === 0) {
          container.innerHTML = '<div class="empty-state">🟢 All clear: No actions pending human approval.</div>';
        } else {
          container.innerHTML = data.cards.map(card => `
            <div class="card pending-approval" id="card-${card.id}">
              <div class="card-header">
                <div class="card-title">${card.title}</div>
              </div>
              <div class="card-meta">
                ID: <strong>${card.id}</strong> | ${card.subtitle}<br>
                Action: <span style="color:#38bdf8">${card.action_type}</span>
              </div>
              ${card.payload && Object.keys(card.payload).length > 0 ?
                `<pre class="card-payload">${JSON.stringify(card.payload, null, 2)}</pre>` : ''}
              ${card.next_unblocked_task ?
                `<div style="font-size:0.75rem; color:var(--muted); margin-bottom:10px;">
                  🔄 Next autonomous task: ${card.next_unblocked_task}
                </div>` : ''}
              <div class="card-actions">
                <button class="btn-approve" onclick="decideApproval('${card.id}', 'approve')">
                  ✅ Approve
                </button>
                <button class="btn-reject" onclick="decideApproval('${card.id}', 'reject')">
                  ❌ Reject
                </button>
              </div>
            </div>
          `).join('');
        }

        // Render history
        const histContainer = document.getElementById('history-container');
        if (data.history && data.history.length > 0) {
          histContainer.innerHTML = data.history.slice(0, 5).map(h => `
            <div class="card" style="padding:10px 14px; font-size:0.85rem;">
              <div style="display:flex; justify-content:space-between; align-items:center;">
                <strong>${h.title || h.id}</strong>
                <span style="color:${h.status === 'APPROVED' ? 'var(--success)' : 'var(--danger)'}; font-weight:700;">
                  ${h.status}
                </span>
              </div>
              <div style="font-size:0.75rem; color:var(--muted); margin-top:4px;">
                By: ${h.resolved_by || 'operator'} at ${h.resolved_at ? h.resolved_at.slice(0, 19).replace('T', ' ') : ''}
              </div>
            </div>
          `).join('');
        } else {
          histContainer.innerHTML = '<div class="empty-state">No historical approvals yet.</div>';
        }
      } catch (err) {
        console.error('Failed to load approvals:', err);
      }
    }

    async function loadNodeMap() {
      try {
        const resp = await fetch(API_BASE + '/v1/nodes', { headers: getHeaders() });
        if (!resp.ok) return;
        const data = await resp.json();
        const nodes = data.nodes || [];
        const onlineCount = nodes.filter(n => n.status === 'online').length;
        document.getElementById('node-online-count').innerText = `${onlineCount} / ${nodes.length} online`;

        const container = document.getElementById('nodes-container');
        if (nodes.length === 0) {
          container.innerHTML = '<div class="empty-state">No registered nodes found.</div>';
          return;
        }

        container.innerHTML = nodes.map(n => {
          const isOnline = n.status === 'online';
          const osIcon = n.platform === 'Linux' ? '🐧' : (n.platform === 'Windows' ? '🪟' : (n.platform === 'Darwin' ? '🍎' : '💻'));
          const surfaces = (n.surface_inventory && n.surface_inventory.surfaces || []).map(s => s.provider).filter(Boolean);
          const surfaceTags = surfaces.length > 0 ? surfaces.map(s => `<span style="font-size:0.7rem; background:#1e293b; padding:2px 6px; border-radius:4px; margin-right:4px;">${s}</span>`).join('') : '<span style="font-size:0.7rem; color:var(--muted);">no agents</span>';
          const heartbeatSec = n.heartbeat_age_seconds !== null && n.heartbeat_age_seconds !== undefined ? `${n.heartbeat_age_seconds}s ago` : 'never';

          return `
            <div class="card" style="padding:12px 14px; margin-bottom:8px; border-left: 4px solid ${isOnline ? 'var(--success)' : 'var(--danger)'};">
              <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">
                <div style="font-weight:700; color:#fff; display:flex; align-items:center; gap:6px;">
                  <span>${osIcon}</span>
                  <span>${n.node_id}</span>
                  <span style="font-size:0.75rem; font-weight:400; color:var(--muted);">(${n.hostname || 'unknown'})</span>
                </div>
                <span style="font-size:0.75rem; font-weight:700; color:${isOnline ? 'var(--success)' : 'var(--danger)'};">
                  ${isOnline ? '🟢 ONLINE' : '🔴 OFFLINE'}
                </span>
              </div>
              <div style="font-size:0.75rem; color:var(--muted); margin-bottom:6px;">
                Role: <strong>${n.role || 'client'}</strong> | Heartbeat: <span style="color:#e2e8f0;">${heartbeatSec}</span> | OS: ${n.platform || 'Unknown'}
              </div>
              <div style="margin-top:4px;">${surfaceTags}</div>
            </div>
          `;
        }).join('');
      } catch (err) {
        console.error('Failed to load node map:', err);
      }
    }

    async function approveNodeCode() {
      const input = document.getElementById('node-join-code');
      const code = input.value.trim().toUpperCase();
      const resDiv = document.getElementById('node-approve-result');
      const btn = document.getElementById('btn-approve-node');

      if (!code) {
        alert('Please enter a User Code.');
        return;
      }

      btn.disabled = true;
      btn.innerText = 'Approving Node...';
      resDiv.style.display = 'none';

      try {
        const resp = await fetch(API_BASE + '/v1/nodes/approve', {
          method: 'POST',
          headers: getHeaders(),
          body: JSON.stringify({ code: code })
        });
        const data = await resp.json();
        resDiv.style.display = 'block';
        if (resp.ok && data.success) {
          resDiv.innerHTML = `
            <div style="background:#064e3b; border:1px solid #059669; padding:10px; border-radius:8px; font-size:0.85rem;">
              ✅ <strong>Node Approved!</strong><br>
              Node ID: <code>${data.node_id}</code><br>
              Code: <code>${data.user_code}</code>
            </div>
          `;
          input.value = '';
          showToast(`Node ${data.node_id} approved!`);
          loadNodeMap();
        } else {
          resDiv.innerHTML = `
            <div style="background:#7f1d1d; border:1px solid #dc2626; padding:10px; border-radius:8px; font-size:0.85rem;">
              ❌ Approval failed: ${data.error || 'Unknown error'}
            </div>
          `;
        }
      } catch (err) {
        resDiv.style.display = 'block';
        resDiv.innerHTML = `
          <div style="background:#7f1d1d; border:1px solid #dc2626; padding:10px; border-radius:8px; font-size:0.85rem;">
            ❌ Network error: ${err.message}
          </div>
        `;
      } finally {
        btn.disabled = false;
        btn.innerText = '🛡️ Approve';
      }
    }

    async function decideApproval(id, decision) {
      try {
        const btn = event.target;
        btn.disabled = true;
        btn.innerText = 'Processing...';

        const resp = await fetch(API_BASE + '/v1/approvals/decide', {
          method: 'POST',
          headers: getHeaders(),
          body: JSON.stringify({
            id: id,
            decision: decision,
            approver: 'Alston (Mobile Web)'
          })
        });

        const result = await resp.json();
        if (result.success) {
          showToast(`Approval ${id} marked ${decision.toUpperCase()}`);
          loadApprovals();
        } else {
          showToast(`Error: ${result.error || 'Failed to process'}`);
          btn.disabled = false;
        }
      } catch (err) {
        showToast('Network error: ' + err.message);
      }
    }

    async function dispatchTask() {
      const capability = document.getElementById('task-capability').value;
      const goal = document.getElementById('task-goal').value.trim();
      const resDiv = document.getElementById('dispatch-result');
      const btn = document.getElementById('btn-dispatch');

      if (!goal) {
        alert('Please enter a goal description.');
        return;
      }

      btn.disabled = true;
      btn.innerText = '⏳ Dispatching to Oracle Local...';
      resDiv.style.display = 'none';

      try {
        const resp = await fetch(API_BASE + '/v1/tasks', {
          method: 'POST',
          headers: getHeaders(),
          body: JSON.stringify({
            project_id: 'agentmanager',
            goal: goal,
            capability: capability,
            payload: { client: 'agentos-mobile-companion' }
          })
        });

        const data = await resp.json();
        resDiv.style.display = 'block';
        if (resp.status === 200 || resp.status === 202) {
          const taskId = data.task ? (data.task.taskId || data.task.id) : 'submitted';
          resDiv.innerHTML = `
            <div style="background:#064e3b; border:1px solid #059669; padding:10px; border-radius:8px; font-size:0.85rem;">
              ✅ <strong>Task Dispatched!</strong><br>
              Task ID: <code>${taskId}</code><br>
              Status: <code>${data.task ? (data.task.status || data.task.state) : 'submitted'}</code>
            </div>
          `;
          document.getElementById('task-goal').value = '';
          showToast('Task submitted successfully!');
        } else {
          resDiv.innerHTML = `
            <div style="background:#7f1d1d; border:1px solid #dc2626; padding:10px; border-radius:8px; font-size:0.85rem;">
              ❌ Submission failed: ${data.message || data.error || 'Unknown error'}
            </div>
          `;
        }
      } catch (err) {
        resDiv.style.display = 'block';
        resDiv.innerHTML = `
          <div style="background:#7f1d1d; border:1px solid #dc2626; padding:10px; border-radius:8px; font-size:0.85rem;">
            ❌ Network error: ${err.message}
          </div>
        `;
      } finally {
        btn.disabled = false;
        btn.innerText = '🚀 Submit Task to Local Executor';
      }
    }

    // Initial load and periodic polling
    loadApprovals();
    loadNodeMap();
    setInterval(() => {
      loadApprovals();
      loadNodeMap();
    }, 5000);
  </script>
</body>
</html>
"""


def render_companion_html(auth_token: str = "") -> str:
    """Render the AgentOS Web Console HTML.

    ``auth_token`` is accepted only for backward compatibility and is
    deliberately ignored: credentials must never be embedded in served HTML,
    because the console is reachable from the public internet.
    """
    del auth_token
    return HTML_TEMPLATE


# Public homepage is intentionally separate from the privileged operator UI.
# The OAuth routes must be mounted at this hostname before public sign-in
# is considered ready; this HTML alone cannot grant a Realm membership.
PUBLIC_ENTRY_HTML = """<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AgentOS — 登入</title>
<meta name="robots" content="noindex,nofollow">
<style>
:root{color-scheme:dark;font-family:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
body{margin:0;background:#080c14;color:#e5e7eb;display:grid;place-items:center;min-height:100vh}
main{box-sizing:border-box;width:min(92vw,500px);padding:36px;border:1px solid #293244;border-radius:16px;background:#101827}
h1{margin-top:0;font-size:1.8rem}p{line-height:1.7;color:#aab6cb}
a{display:block;text-decoration:none;border-radius:9px;padding:13px;margin-top:12px;text-align:center}
.primary{background:#5564e8;color:white}.secondary{border:1px solid #42516a;color:#e5e7eb}
small{display:block;margin-top:22px;color:#90a0ba}
</style>
</head>
<body>
<main>
<h1>AgentOS</h1>
<p>使用自己的帳號登入 AgentOS。首次使用時，須完成獨立 Realm 的建立或加入授權。</p>
<a class="primary" href="/dashboard/api/auth/signin/google?site=agentos&amp;returnTo=%2F">以 Google 登入</a>
<a class="secondary" href="/dashboard/api/auth/signin/github?site=agentos&amp;returnTo=%2F">以 GitHub 登入</a>
<a class="secondary" href="/dashboard/api/auth/signin/facebook?site=agentos&amp;returnTo=%2F">以 Facebook 登入</a>
<a class="secondary" href="/dashboard/api/auth/signin/line?site=agentos&amp;returnTo=%2F">以 LINE 登入</a>
<small>一般使用者不需要 Operator Token。登入後的 Realm 權限必須由 ONE 驗證，未取得授權時不得進入管理 Console。</small>
<p id="session-state" aria-live="polite"></p>
<script>
(async () => {
  try {
    const response = await fetch('/dashboard/api/auth/session', {credentials:'same-origin', cache:'no-store'});
    if (!response.ok) return;
    const session = await response.json();
    if (session.loggedIn !== true) return;
    document.querySelectorAll('a.primary,a.secondary').forEach(link => { link.hidden = true; });
    const state = document.getElementById('session-state');
    state.textContent = '帳號已登入。Realm 建立或加入授權尚未完成；不會自動進入管理者 Console。';
  } catch { /* Keep sign-in options visible if OAuth endpoint is unavailable. */ }
})();
</script>
</main>
</body>
</html>
"""


def render_public_entry_html() -> str:
    """Unauthenticated landing: no operator UI, token prompt, or Realm data."""
    return PUBLIC_ENTRY_HTML
