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
<a class="primary" href="/dashboard/api/auth/signin/google?site=agentos&amp;returnTo=%2Fwelcome">以 Google 登入</a>
<a class="secondary" href="/dashboard/api/auth/signin/github?site=agentos&amp;returnTo=%2Fwelcome">以 GitHub 登入</a>
<a class="secondary" href="/dashboard/api/auth/signin/facebook?site=agentos&amp;returnTo=%2Fwelcome">以 Facebook 登入</a>
<a class="secondary" href="/dashboard/api/auth/signin/line?site=agentos&amp;returnTo=%2Fwelcome">以 LINE 登入</a>
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

# A separate, non-privileged post-OAuth destination. The old root is always
# the sign-in screen; redirecting OAuth callbacks there looked like an endless
# login loop even when the provider had accepted the user.
WELCOME_HTML = """<!doctype html>
<html lang="zh-Hant">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex,nofollow"><title>AgentOS — 登入狀態</title>
<style>
:root{color-scheme:dark;font-family:system-ui,-apple-system,sans-serif}
body{background:#080c14;color:#e5e7eb;display:grid;place-items:center;min-height:100vh;margin:0}
main{padding:36px;border:1px solid #293244;border-radius:16px;background:#101827;width:min(88vw,500px)}
p{line-height:1.7;color:#aab6cb}a{color:#9baaff}
button,input{font:inherit;border:1px solid #42516a;border-radius:8px;padding:10px;background:#172238;color:#f3f4f6}
button{cursor:pointer;margin:6px 6px 6px 0}button:disabled{opacity:.5;cursor:not-allowed}
input{width:95%;box-sizing:border-box}.actions{margin-top:14px}
</style></head><body><main>
<h1>AgentOS</h1>
<nav aria-label="AgentOS 主要導覽" style="display:flex;flex-wrap:wrap;gap:14px;padding:10px 0 20px">
<a href="/welcome" aria-current="page">我的 AgentOS</a>
<a href="/platform">平台治理（需管理權限）</a>
<a href="/">登入首頁</a>
</nav>
<p id="login-status" aria-live="polite">正在確認登入狀態…</p>
<section id="realm-onboarding" hidden>
<h2>我的 Realm</h2>
<p id="realm-status" aria-live="polite">正在讀取開通狀態…</p>
<div id="realm-actions" class="actions" hidden>
<p>第一次使用可提出建立個人 Realm 的申請；已有 Realm 則可以申請加入。申請送交治理審核，不會立即取得其他 Realm 權限。</p>
<button id="create-realm" type="button">申請建立個人 Realm</button>
<label for="join-realm">既有 Realm ID</label>
<input id="join-realm" placeholder="例如 realm-example" maxlength="63" autocomplete="off">
<button id="join-realm-submit" type="button">申請加入既有 Realm</button>
</div>
</section>
<p id="next-action" hidden><a href="/">返回登入頁</a></p>
<script>
(async () => {
  const status = document.getElementById('login-status');
  const retry = document.getElementById('next-action');
  try {
    const response = await fetch('/dashboard/api/auth/session', {
      credentials:'same-origin', cache:'no-store'
    });
    if (!response.ok) throw new Error('session_unavailable');
    const session = await response.json();
    if (session.loggedIn === true && session.provider && session.subject) {
      status.textContent = '已使用 ' + session.provider + ' 登入 AgentOS。管理者 Console 不會自動開放。';
      const onboarding = document.getElementById('realm-onboarding');
      const current = document.getElementById('realm-status');
      const actions = document.getElementById('realm-actions');
      onboarding.hidden = false;
      const endpoint = '/v1/account/realm-request';
      const readStatus = async () => {
        const answer = await fetch(endpoint, {credentials:'same-origin', cache:'no-store'});
        if (!answer.ok) throw new Error('realm_read_unavailable');
        return answer.json();
      };
      const showStatus = data => {
        // Governance approval and an active ONE are deliberately different
        // states. Navigation remains available regardless of either state.
        if (data.state === 'pending_review') {
          current.textContent = '申請已建立（' + data.request_id +
            '），類型：' + (data.kind === 'create' ? '建立新 Realm' : '加入既有 Realm') +
            '。目前等待治理審核，尚未開通。';
          actions.hidden = true;
        } else if (data.state === 'approved_pending_provisioning') {
          current.textContent = '申請 ' + data.request_id +
            ' 已經治理核准，但仍等待 ONE 正式開通與帳號授權。此時還不能使用 Realm。';
          actions.hidden = true;
        } else if (data.state === 'realm_initialized') {
          current.textContent = '已建立獨立 Realm：' + data.realm_id +
            '，且此帳號已綁定為 Owner。ONE 執行服務尚待進一步啟動驗收。';
          actions.hidden = true;
          if (!document.getElementById('my-one-link')) {
            const link = document.createElement('a');
            link.id = 'my-one-link';
            link.href = '/my-one';
            link.textContent = '開啟我的 Virtual ONE（Realm 基本資訊）';
            current.after(link);
          }
        } else if (data.state === 'rejected') {
          current.textContent = '申請 ' + data.request_id + ' 已被拒絕，未建立 Realm。';
          actions.hidden = true;
        } else {
          current.textContent = '尚未有 Realm 開通申請。';
          actions.hidden = false;
        }
      };
      try {
        showStatus(await readStatus());
      } catch {
        current.textContent = 'Realm 開通服務暫時無法連線。登入已成功，但尚未取得 Realm 權限。';
      }
      async function submit(kind) {
        const realm_id = document.getElementById('join-realm').value.trim().toLowerCase();
        if (kind === 'join' && !/^[a-z][a-z0-9-]{2,62}$/.test(realm_id)) {
          current.textContent = '請輸入有效的 Realm ID（小寫字母、數字、連字號，3 至 63 字）。';
          return;
        }
        actions.querySelectorAll('button').forEach(b => { b.disabled = true; });
        try {
          const response = await fetch(endpoint, {
            method:'POST', credentials:'same-origin',
            headers:{'Content-Type':'application/json'},
            body:JSON.stringify(kind === 'join' ? {kind,realm_id} : {kind})
          });
          const data = await response.json();
          if (!response.ok) throw new Error(data.error || 'registration_unavailable');
          showStatus(data);
        } catch {
          current.textContent = '無法提交 Realm 申請。請檢查服務狀態後重試。';
          actions.querySelectorAll('button').forEach(b => { b.disabled = false; });
        }
      }
      document.getElementById('create-realm').onclick = () => submit('create');
      document.getElementById('join-realm-submit').onclick = () => submit('join');
      return;
    }
    status.textContent = 'Google 授權已返回 AgentOS，但網站未取得有效的登入 Session。請重新登入；若仍發生，需檢查瀏覽器 Cookie 與伺服器認證回呼。';
  } catch {
    status.textContent = '無法確認 AgentOS 登入 Session。請檢查認證服務狀態後重試。';
  }
  retry.hidden = false;
})();
</script></main></body></html>
"""


def render_welcome_html() -> str:
    """Unprivileged post-login status; never treat a browser cookie as ONE authority."""
    return WELCOME_HTML

PLATFORM_REVIEW_HTML = """<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AgentOS — 平台治理</title><meta name="robots" content="noindex,nofollow">
<style>
:root{color-scheme:dark;font:15px system-ui,-apple-system,sans-serif}
*{box-sizing:border-box}body{margin:0;background:#080c14;color:#e5e7eb}
header{border-bottom:1px solid #293244;background:#101827;padding:18px clamp(18px,4vw,48px)}
main{max-width:1180px;margin:auto;padding:28px 20px}
h1{font-size:24px;margin:0 0 6px}h2{font-size:19px}h3{font-size:16px;margin:0 0 10px}
p,dt{color:#abb8ca;line-height:1.6}nav{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}
nav a{border:1px solid #3f5066;border-radius:8px;padding:9px 12px;color:#e5e7eb;text-decoration:none}
nav a.active{background:#263d68}nav a[aria-disabled=true]{opacity:.55;cursor:default}
a{color:#acc6ff}.stats{display:flex;flex-wrap:wrap;gap:12px;margin:16px 0 22px}
.stat{background:#111c2d;border:1px solid #293244;border-radius:12px;padding:14px 20px;min-width:150px}
.stat strong{display:block;font-size:26px}.stat span{font-size:12px;color:#abb8ca}
article{border:1px solid #344256;background:#101827;border-radius:12px;padding:20px;margin:14px 0}
dl{display:grid;grid-template-columns:repeat(auto-fit,minmax(205px,1fr));gap:10px 18px}
dt{font-size:12px}dd{margin:2px 0 0;overflow-wrap:anywhere}
button{font:inherit;color:white;background:#244477;border:1px solid #45669a;border-radius:8px;padding:10px 14px;margin:5px 8px 5px 0;cursor:pointer}
button.danger{background:#3e2931;border-color:#8b4655}button:disabled{opacity:.45;cursor:not-allowed}
code{overflow-wrap:anywhere;color:#c8d6f4}small,.muted{color:#90a3ba}
</style></head><body>
<header><h1>AgentOS 平台治理中心</h1>
<p>平台管理員工作區 · 與各 Realm 的 Virtual ONE 分離</p>
<nav aria-label="平台功能">
<a class="active" href="/platform" aria-current="page">Realm 開通審核</a>
<a aria-disabled="true" title="尚未提供平台層級介面">Realm 清冊（尚未開放）</a>
<a aria-disabled="true" title="尚未提供平台層級介面">節點與資源（尚未開放）</a>
<a aria-disabled="true" title="尚未提供平台層級介面">治理與回執（尚未開放）</a>
<a href="/welcome">我的 AgentOS</a>
</nav></header>
<main>
<p>這裡管理平台層級的開通申請。Realm 的日常操作應由各自授權的 Virtual ONE 處理；核准申請不等於 ONE 已建立。</p>
<div class="stats">
<div class="stat"><strong id="pending-count">—</strong><span>待審申請</span></div>
<div class="stat"><strong id="history-count">—</strong><span>近期審核紀錄</span></div>
<div class="stat"><strong>獨立</strong><span>Realm 權限邊界</span></div>
</div>
<h2>待審核的 Realm 申請</h2>
<p id="review-status" role="status" aria-live="polite">正在讀取審核資料…</p>
<section id="pending"></section>
<h2>近期審核紀錄</h2>
<section id="history"></section>
</main>
<script>
const endpoint='/v1/platform/realm-requests';
const status=document.getElementById('review-status');
const pending=document.getElementById('pending'),history=document.getElementById('history');
function field(dl,key,val){
 const wrap=document.createElement('div');
 const dt=document.createElement('dt'),dd=document.createElement('dd');
 dt.textContent=key;dd.textContent=val===null||val===undefined||val===''?'—':String(val);
 wrap.append(dt,dd);dl.append(wrap);
}
function card(item,canDecide){
 const el=document.createElement('article');
 const title=document.createElement('h3');
 title.textContent=item.kind==='create'?'建立新的獨立 Realm':'申請加入既有 Realm';
 el.append(title);
 const dl=document.createElement('dl'),person=item.applicant||{};
 field(dl,'申請人',person.name||'未提供（舊申請）');
 field(dl,'登入來源',person.provider||'unknown');
 field(dl,'申請人識別碼',item.applicant_ref||'—');
 field(dl,'申請類型',item.kind==='create'?'建立':'加入');
 field(dl,'申請時間',item.parked_at||'未記錄');
 field(dl,'審核狀態',item.stage||item.status);
 field(dl,'目標 Realm',item.kind==='create'?'新 Realm（尚未配置 ID）':item.realm_id);
 field(dl,'Realm 初始化',item.provisioned===true?'獨立資料與 Owner 綁定已驗證':'尚未初始化');
 field(dl,'ONE 執行服務',item.one_runtime_attested===true?'已驗證':'尚未驗收');
 field(dl,'下一階段',item.provisioned===true?'等待 ONE 執行服務及節點能力驗收':item.status==='APPROVED'?'等待獨立 ONE 建立與帳號 Owner 綁定':'等待平台審核');
 field(dl,'申請編號',item.request_id);
 if(item.resolved_at)field(dl,'審核時間',item.resolved_at);
 if(item.resolved_by)field(dl,'審核人識別',item.resolved_by);
 el.append(dl);
 if(canDecide){
   for(const decision of ['approve','reject']){
     const btn=document.createElement('button');
     btn.textContent=decision==='approve'?'核准申請（不代表開通）':'拒絕申請';
     if(decision==='reject')btn.className='danger';
     btn.onclick=async()=>{
       if(!confirm('確定'+(decision==='approve'?'核准':'拒絕')+'這筆申請？此操作將留下治理紀錄。'))return;
       el.querySelectorAll('button').forEach(b=>b.disabled=true);
       try{
         const res=await fetch(endpoint,{method:'POST',credentials:'same-origin',
           headers:{'Content-Type':'application/json'},
           body:JSON.stringify({request_id:item.request_id,decision})});
         if(!res.ok)throw Error('審核失敗（'+res.status+'），請重新查詢');
         await load();
       }catch(e){status.textContent=e.message;el.querySelectorAll('button').forEach(b=>b.disabled=false);}
     };el.append(btn);
   }
 }return el;
}
async function load(){
 try{
  const res=await fetch(endpoint,{credentials:'same-origin',cache:'no-store'});
  if(!res.ok)throw Error('無法讀取審核資料（'+res.status+'）');
  const data=await res.json();
  document.getElementById('pending-count').textContent=data.pending.length;
  document.getElementById('history-count').textContent=data.history.length;
  status.textContent=data.pending.length+' 筆待審申請。審核完成後仍須 ONE 的正式開通回執；已核准申請會移至下方近期審核紀錄。';
  pending.replaceChildren();history.replaceChildren();
  for(const item of data.pending)pending.append(card(item,true));
  for(const item of data.history)history.append(card(item,false));
  if(!data.pending.length){const p=document.createElement('p');p.textContent='目前沒有待審申請。';pending.append(p);}
  if(!data.history.length){const p=document.createElement('p');p.textContent='尚無審核紀錄。';history.append(p);}
 }catch(e){status.textContent=e.message||'無法載入';}
}
load();
</script></body></html>
"""


def render_platform_review_html() -> str:
    return PLATFORM_REVIEW_HTML


PLATFORM_LOGIN_REQUIRED_HTML = """<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex,nofollow"><title>AgentOS — 平台管理員登入</title>
<style>
:root{color-scheme:dark;font-family:system-ui,-apple-system,sans-serif}
body{background:#080c14;color:#e5e7eb;display:grid;place-items:center;min-height:100vh;margin:0}
main{padding:32px;border:1px solid #293244;border-radius:16px;background:#101827;width:min(90vw,540px)}
p{color:#aab6cb;line-height:1.7}a{display:inline-block;color:#b6caff;margin:6px 12px 6px 0}
</style></head><body><main>
<h1>AgentOS 平台治理</h1>
<p>需要使用已獲授權的平台管理者帳號登入。</p>
<nav aria-label="管理者登入選項">
<a href="/dashboard/api/auth/signin/google?site=agentos&amp;returnTo=%2Fplatform">以 Google 登入</a>
<a href="/dashboard/api/auth/signin/github?site=agentos&amp;returnTo=%2Fplatform">以 GitHub 登入</a>
<a href="/dashboard/api/auth/signin/facebook?site=agentos&amp;returnTo=%2Fplatform">以 Facebook 登入</a>
<a href="/dashboard/api/auth/signin/line?site=agentos&amp;returnTo=%2Fplatform">以 LINE 登入</a>
</nav>
<p><a href="/welcome">返回我的 Realm 申請</a></p>
</main></body></html>
"""

PLATFORM_SWITCH_ACCOUNT_HTML = """<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex,nofollow"><title>AgentOS — 切換平台管理帳號</title>
<style>
:root{color-scheme:dark;font-family:system-ui,-apple-system,sans-serif}
body{background:#080c14;color:#e5e7eb;display:grid;place-items:center;min-height:100vh;margin:0}
main{padding:32px;border:1px solid #293244;border-radius:16px;background:#101827;width:min(90vw,540px)}
p{color:#aab6cb;line-height:1.7}a{display:inline-block;color:#b6caff;margin:6px 12px 6px 0}
</style></head><body><main>
<h1>目前帳號沒有平台管理權限</h1>
<p>你已登入 AgentOS，但此帳號不是獲授權的平台管理者。
你仍可查看自己的 Realm 申請，或切換為有權限的帳號。</p>
<p><a href="/dashboard/api/auth/logout?returnTo=%2Fplatform">登出並切換管理帳號</a></p>
<p><a href="/welcome">返回我的 Realm 申請</a></p>
</main></body></html>
"""


def render_platform_auth_gate_html(*, authenticated: bool) -> str:
    """Public, non-sensitive denial UI. Protected review data stays server-gated."""
    return PLATFORM_SWITCH_ACCOUNT_HTML if authenticated else PLATFORM_LOGIN_REQUIRED_HTML

MY_ONE_HTML = """<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow"><title>AgentOS — 我的 Virtual ONE</title>
<style>:root{color-scheme:dark;font-family:system-ui,sans-serif}
body{background:#080c14;color:#e5e7eb;min-height:100vh;margin:0}
main{max-width:760px;margin:7vh auto;padding:28px;background:#101827;border:1px solid #293244;border-radius:14px}
a{color:#b5c7fa}p{color:#aab6cb;line-height:1.6}
dl{display:grid;grid-template-columns:180px 1fr;gap:12px}dd{margin:0}
section{padding:16px 0;border-top:1px solid #293244;margin-top:18px}
button,input{font:inherit;padding:10px;background:#1c2d49;color:#edf2ff;border:1px solid #526582;border-radius:8px}
button{cursor:pointer;margin:6px 6px 6px 0}input{min-width:170px;max-width:95%}
article{border:1px solid #34465c;background:#142036;padding:12px;border-radius:8px;margin:10px 0}
small{color:#9eafc5}
</style></head><body><main>
<h1>我的 Virtual ONE</h1>
<nav><a href="/welcome">我的 AgentOS</a> · <a href="/platform">平台治理（需管理權限）</a></nav>
<p>此頁提供獨立 Realm 的 Node Map 與 Node 加入核准。ONE 執行服務及任務派送仍須正式驗收。</p>
<p id="status" role="status">正在確認 Realm Owner 權限…</p>
<dl id="details" hidden>
<dt>Realm ID</dt><dd id="realm-id"></dd>
<dt>帳號角色</dt><dd id="owner-role"></dd>
<dt>已加入節點</dt><dd id="node-count"></dd>
<dt>ONE 執行服務</dt><dd id="one-runtime"></dd>
</dl>
<section id="node-management" hidden>
<h2>Node Map</h2>
<p id="map-status" role="status">讀取節點中…</p>
<div id="node-map"></div>
<h2>加入 Node</h2>
<p>在新 Node 安裝程式選擇此 Realm，產生一次性 Code 後，在此輸入核准。核准後 Node 仍須完成 claim 才算加入。</p>
<p><small>Realm ID：<code id="join-target"></code></small></p>
<p><small>此 Realm 的 Node 申請 API：<code id="join-endpoint"></code></small></p>
<label for="node-code">Node 上顯示的 8 碼 Code</label>
<input id="node-code" placeholder="ABCD-EFGH" maxlength="9" autocomplete="off">
<button type="button" id="approve-node">核准加入 Node</button>
<p id="join-status" role="status"></p>
<h3>待處理 Node 申請</h3><div id="pending-joins"></div>
</section>
<script>
async function refreshNodeMap(){
 const res=await fetch('/v1/account/virtual-one/nodes',{credentials:'same-origin',cache:'no-store'});
 if(!res.ok)throw Error('無法取得這個 Realm 的 Node Map');
 const data=await res.json();
 document.getElementById('map-status').textContent='已加入 '+data.node_count+' 台，線上 '+data.online_node_count+' 台。';
 const map=document.getElementById('node-map'),pending=document.getElementById('pending-joins');
 map.replaceChildren();pending.replaceChildren();
 for(const node of data.nodes){
  const entry=document.createElement('article');
  const name=document.createElement('strong');name.textContent=node.node_id||'未命名 Node';
  const detail=document.createElement('p');
  detail.textContent=(node.status||'unknown')+' · '+(node.role||'client')+
   ' · 能力：'+(Array.isArray(node.capabilities)?node.capabilities.join('、'):'—');
  entry.append(name,detail);map.append(entry);
 }
 if(!data.nodes.length){const p=document.createElement('p');p.textContent='此 Realm 尚未有 Node。';map.append(p);}
 for(const request of data.pending_joins){
  const p=document.createElement('p');
  p.textContent=request.node_id+' · '+request.user_code+
     ' · '+(request.approved?'已核准，等待 Node 領取':'等待核准')+
     ' · 到期 '+request.expires_at;pending.append(p);
 }
 if(!data.pending_joins.length){const p=document.createElement('p');p.textContent='目前沒有待處理加入申請。';pending.append(p);}
}
document.getElementById('approve-node').onclick=async()=>{
 const input=document.getElementById('node-code');
 const code=input.value.trim().toUpperCase();
 const msg=document.getElementById('join-status');
 if(!/^[A-Z2-9]{4}-[A-Z2-9]{4}$/.test(code)){msg.textContent='請輸入有效的 Node 加入 Code。';return;}
 const btn=document.getElementById('approve-node');btn.disabled=true;
 try{
  const res=await fetch('/v1/account/virtual-one/join/approve',{
   method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},
   body:JSON.stringify({code})
  });
  const data=await res.json();
  if(!res.ok)throw Error(data.error||'核准失敗');
  msg.textContent='已核准 '+data.node_id+'，等待 Node 領取憑證。';
  input.value='';await refreshNodeMap();
 }catch(e){msg.textContent=e.message||'無法完成核准';}
 finally{btn.disabled=false;}
};
(async()=>{
const status=document.getElementById('status');
try{
const res=await fetch('/v1/account/virtual-one',{credentials:'same-origin',cache:'no-store'});
if(!res.ok)throw Error(res.status===403?'此帳號尚未綁定可使用的 Realm':'無法讀取 Realm 資訊');
const data=await res.json();
document.getElementById('realm-id').textContent=data.realm_id;
document.getElementById('owner-role').textContent=data.role;
document.getElementById('node-count').textContent=String(data.node_count);
document.getElementById('one-runtime').textContent=data.one_runtime_attested?'已驗證':'尚未驗收';
document.getElementById('details').hidden=false;
status.textContent='已完成獨立 Realm 資料初始化及帳號擁有者綁定。';
document.getElementById('join-target').textContent=data.realm_id;
document.getElementById('join-endpoint').textContent=location.origin+'/v1/realms/'+data.realm_id+'/join/request';
document.getElementById('node-management').hidden=false;
try{await refreshNodeMap();}catch(e){document.getElementById('map-status').textContent=e.message;}
}catch(e){status.textContent=e.message;}
})();
</script></main></body></html>
"""


def render_my_one_html() -> str:
    return MY_ONE_HTML
