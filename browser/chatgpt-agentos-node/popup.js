async function activeChatKey() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.url) throw new Error('找不到目前分頁');
  const url = new URL(tab.url);
  if (!['chatgpt.com', 'chat.openai.com'].includes(url.host)) {
    throw new Error('目前分頁不是 ChatGPT');
  }
  return `conversation:${url.host}${url.pathname}`;
}

async function refresh() {
  const status = document.getElementById('status');
  try {
    const key = await activeChatKey();
    const values = await chrome.storage.local.get([key, 'activeProjectId', 'companionToken']);
    document.getElementById('project').value = values[key] || values.activeProjectId || '';
    document.getElementById('token').value = values.companionToken || '';
    status.textContent = values[key] ? `目前 Chat 已綁定：${values[key]}` : '目前 Chat 尚未綁定；會以 active project 作為 rollover fallback。';
  } catch (error) {
    status.textContent = error.message;
  }
}

document.getElementById('bind').addEventListener('click', async () => {
  const status = document.getElementById('status');
  try {
    const projectId = document.getElementById('project').value.trim();
    if (!projectId) throw new Error('請輸入 project_id');
    const key = await activeChatKey();
    await chrome.storage.local.set({ [key]: projectId, activeProjectId: projectId });
    status.textContent = `已綁定目前 Chat → ${projectId}`;
  } catch (error) {
    status.textContent = error.message;
  }
});

document.getElementById('saveToken').addEventListener('click', async () => {
  const status = document.getElementById('status');
  const token = document.getElementById('token').value.trim();
  if (token.length < 24) {
    status.textContent = 'Companion token 至少需要 24 字元';
    return;
  }
  await chrome.storage.local.set({ companionToken: token });
  status.textContent = 'Companion token 已儲存於 extension local storage。';
});

refresh();
