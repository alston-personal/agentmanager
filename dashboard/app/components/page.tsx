'use client';

import { useEffect, useRef } from 'react';

export default function ComponentsPage() {
  const hostRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const script = document.createElement('script');
    script.src = '/dashboard/components/agentos-thumbnail-picker.js';
    script.onload = () => {
      const picker = document.createElement('agentos-thumbnail-picker') as HTMLElement & { items: unknown[] };
      picker.setAttribute('placeholder', '選擇一個項目');
      picker.items = [
        { id: 'ip-genome', name: 'IP Genome Studio', thumbnail: '/dashboard/components/agentos-thumbnail-picker.js' },
        { id: 'knowledge', name: 'Knowledge Vault', thumbnail: '/dashboard/components/agentos-thumbnail-picker.js' },
      ];
      hostRef.current?.replaceChildren(picker);
    };
    document.head.append(script);
    return () => script.remove();
  }, []);

  const usage = "const picker = document.querySelector('agentos-thumbnail-picker');\npicker.items = [{ id: 'yuna', name: 'Yuna', thumbnail: '/yuna.jpg' }];\npicker.addEventListener('change', (event) => console.log(event.detail));";

  return (
    <main style={{ minHeight: '100vh', padding: '3rem 1.5rem' }}>
      <div className="container" style={{ maxWidth: 900 }}>
        <p style={{ color: 'var(--color-text-muted)', letterSpacing: '0.12em', textTransform: 'uppercase' }}>AgentOS UI Library</p>
        <h1 className="gradient-text" style={{ fontSize: '2.5rem', fontWeight: 800, marginBottom: '0.75rem' }}>可下載 UI 元件</h1>
        <p style={{ color: 'var(--color-text-secondary)', marginBottom: '2rem' }}>各專案可重用、經過實際產品驗證的 AgentOS 介面元件。</p>
        <section className="glass" style={{ padding: '1.5rem', borderRadius: '1rem', marginBottom: '1rem' }}>
          <h2 style={{ marginBottom: '0.5rem' }}>AgentOS Thumbnail Picker</h2>
          <p style={{ color: 'var(--color-text-secondary)', marginBottom: '1rem' }}>帶縮圖與名稱的自訂選擇器，適合 IP、專案、角色與資產切換。</p>
          <div ref={hostRef} />
          <a className="btn btn-secondary" style={{ display: 'inline-flex', marginTop: '1rem' }} href="/dashboard/components/agentos-thumbnail-picker.js" download>下載 Web Component</a>
          <pre style={{ marginTop: '1rem', whiteSpace: 'pre-wrap', color: 'var(--color-text-secondary)' }}>{usage}</pre>
        </section>
      </div>
    </main>
  );
}
