(() => {
  const CONTINUATION_RE = /^\s*(繼續(?:完成)?|continue|resume)\b?/i;
  const GOAL_RE = /^\s*\/goal\s+([^\s]+)(?:\s+([\s\S]*))?$/i;
  const COMPANION_URL = 'http://127.0.0.1:8766/v1/resume';

  let busy = false;

  function conversationKey() {
    return `conversation:${location.host}${location.pathname}`;
  }

  function readComposer() {
    const active = document.activeElement;
    if (active && (active.tagName === 'TEXTAREA' || active.isContentEditable)) return active;
    return document.querySelector('textarea, [contenteditable="true"]');
  }

  function composerText(el) {
    if (!el) return '';
    return el.tagName === 'TEXTAREA' ? el.value : (el.innerText || el.textContent || '');
  }

  function replaceComposer(el, text) {
    if (!el) return;
    if (el.tagName === 'TEXTAREA') {
      const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')?.set;
      if (setter) setter.call(el, text); else el.value = text;
      el.dispatchEvent(new Event('input', { bubbles: true }));
    } else {
      el.focus();
      document.execCommand('selectAll', false, null);
      document.execCommand('insertText', false, text);
      el.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: text }));
    }
  }

  function showBanner(message, isError = false) {
    let node = document.getElementById('agentos-continuity-banner');
    if (!node) {
      node = document.createElement('div');
      node.id = 'agentos-continuity-banner';
      Object.assign(node.style, {
        position: 'fixed', right: '16px', bottom: '90px', zIndex: 2147483647,
        maxWidth: '420px', padding: '10px 12px', borderRadius: '8px',
        font: '13px/1.4 system-ui, sans-serif', boxShadow: '0 2px 12px rgba(0,0,0,.25)'
      });
      document.documentElement.appendChild(node);
    }
    node.style.background = isError ? '#4b1111' : '#12211a';
    node.style.color = '#fff';
    node.textContent = message;
    clearTimeout(node.__timer);
    node.__timer = setTimeout(() => node.remove(), 5000);
  }

  async function getRouting(text) {
    const goalMatch = text.match(GOAL_RE);
    if (goalMatch) {
      const projectId = goalMatch[1];
      await chrome.storage.local.set({
        [conversationKey()]: projectId,
        activeProjectId: projectId
      });
      return { projectId, intent: goalMatch[2] || 'continue', boundNow: true };
    }

    const keys = [conversationKey(), 'activeProjectId'];
    const values = await chrome.storage.local.get(keys);
    return {
      projectId: values[conversationKey()] || values.activeProjectId || null,
      intent: text,
      boundNow: false
    };
  }

  async function companionToken() {
    const values = await chrome.storage.local.get(['companionToken']);
    return values.companionToken || '';
  }

  async function resumeThroughOne(el, originalText) {
    if (busy) return false;
    busy = true;
    try {
      const route = await getRouting(originalText);
      if (!route.projectId) {
        showBanner('AgentOS: 此 Chat 尚未綁定 project。先用擴充功能綁定，或輸入 /goal <project-id>。', true);
        return false;
      }
      const token = await companionToken();
      if (!token) {
        showBanner('AgentOS: 尚未設定 companion token。', true);
        return false;
      }

      showBanner(`AgentOS: 正在從 ONE 恢復 ${route.projectId}…`);
      const response = await fetch(COMPANION_URL, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-AgentOS-Companion-Token': token
        },
        body: JSON.stringify({
          project_id: route.projectId,
          user_intent: route.intent
        })
      });
      if (!response.ok) throw new Error(`companion HTTP ${response.status}`);
      const payload = await response.json();
      if (!payload.compiled_prompt || !payload.current_ir_digest) {
        throw new Error('resume packet missing canonical binding');
      }

      await chrome.storage.local.set({
        [conversationKey()]: route.projectId,
        activeProjectId: route.projectId,
        lastResumeDigest: payload.current_ir_digest
      });
      replaceComposer(el, payload.compiled_prompt);
      showBanner(`AgentOS: 已從 ONE 接回 ${route.projectId}，可送出。`);
      return true;
    } catch (error) {
      showBanner(`AgentOS resume 失敗：${error.message}。已阻止直接猜測。`, true);
      return false;
    } finally {
      busy = false;
    }
  }

  function isContinuation(text) {
    return CONTINUATION_RE.test(text) || GOAL_RE.test(text);
  }

  document.addEventListener('keydown', async (event) => {
    if (event.key !== 'Enter' || event.shiftKey || event.ctrlKey || event.altKey || event.metaKey) return;
    const el = readComposer();
    const text = composerText(el).trim();
    if (!text || !isContinuation(text) || text.startsWith('{"protocol":"agentos.chatgpt-resume-prompt/')) return;

    event.preventDefault();
    event.stopImmediatePropagation();
    await resumeThroughOne(el, text);
  }, true);
})();
