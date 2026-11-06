'use client';

import { useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';

export default function ComponentsPage() {
  const hostRef = useRef<HTMLDivElement>(null);
  const [copiedIndex, setCopiedIndex] = useState<number | null>(null);
  const router = useRouter();

  useEffect(() => {
    const script = document.createElement('script');
    script.src = '/dashboard/components/agentos-thumbnail-picker.js';
    script.onload = () => {
      const picker = document.createElement('agentos-thumbnail-picker') as HTMLElement & { items: unknown[] };
      picker.setAttribute('placeholder', '切換專案或 AI 員工');
      picker.items = [
        { id: 'sunlake-milkcat', name: '🌸 澪 (Mio) · 晴湖小築', thumbnail: 'https://pub-832f0f7f98d249f8983088b9a0714b62.r2.dev/mio-avatar.png' },
        { id: 'the-paw', name: '🐾 The Paw · 首席工程師', thumbnail: 'https://pub-832f0f7f98d249f8983088b9a0714b62.r2.dev/paw-avatar.png' },
        { id: 'tiandao-alaya', name: '📖 阿賴耶識 (Alaya) · 修真長卷', thumbnail: 'https://pub-832f0f7f98d249f8983088b9a0714b62.r2.dev/alaya-avatar.png' },
      ];
      hostRef.current?.replaceChildren(picker);
    };
    document.head.append(script);
    return () => script.remove();
  }, []);

  const copyCode = (text: string, index: number) => {
    navigator.clipboard.writeText(text);
    setCopiedIndex(index);
    setTimeout(() => setCopiedIndex(null), 2000);
  };

  const components = [
    {
      title: 'AgentOS Thumbnail Picker (自訂縮圖選擇器)',
      desc: '帶有縮圖頭像與名稱的多功能下拉選擇器，適用於 IP、多角色、群島專案與資產切換。',
      demo: <div ref={hostRef} />,
      downloadUrl: '/dashboard/components/agentos-thumbnail-picker.js',
      usage: `<script src="/dashboard/components/agentos-thumbnail-picker.js"></script>
<agentos-thumbnail-picker id="persona-picker" placeholder="選擇角色..."></agentos-thumbnail-picker>
<script>
  const picker = document.getElementById('persona-picker');
  picker.items = [
    { id: 'mio', name: '澪 (Mio)', thumbnail: '/mio-avatar.png' },
    { id: 'paw', name: 'The Paw', thumbnail: '/paw-avatar.png' }
  ];
  picker.addEventListener('change', e => console.log('Selected:', e.detail));
</script>`
    },
    {
      title: 'AgentOS Live Telemetry Badge (即時脈動指示燈)',
      desc: '反應 AI 員工目前自主活動階段（ACTIVE 綠燈脈動、GUARDING 琥珀色警戒、RESTING 藍色深眠）。',
      demo: (
        <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap', alignItems: 'center' }}>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', padding: '6px 14px', borderRadius: '999px', background: 'rgba(16, 185, 129, 0.15)', border: '1px solid rgba(16, 185, 129, 0.4)', color: '#34d399', fontSize: '0.85rem', fontWeight: 600 }}>
            <span style={{ width: 8, height: 8, borderRadius: '50%', background: '#34d399', boxShadow: '0 0 10px #34d399' }}></span>
            ACTIVE · 運作中 (Cycle 635)
          </span>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', padding: '6px 14px', borderRadius: '999px', background: 'rgba(245, 158, 11, 0.15)', border: '1px solid rgba(245, 158, 11, 0.4)', color: '#fbbf24', fontSize: '0.85rem', fontWeight: 600 }}>
            <span style={{ width: 8, height: 8, borderRadius: '50%', background: '#fbbf24', boxShadow: '0 0 10px #fbbf24' }}></span>
            GUARDING · 安全防線衛戍
          </span>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', padding: '6px 14px', borderRadius: '999px', background: 'rgba(56, 189, 248, 0.15)', border: '1px solid rgba(56, 189, 248, 0.4)', color: '#38bdf8', fontSize: '0.85rem', fontWeight: 600 }}>
            <span style={{ width: 8, height: 8, borderRadius: '50%', background: '#38bdf8', boxShadow: '0 0 10px #38bdf8' }}></span>
            RESTING · 靈感蓄力期
          </span>
        </div>
      ),
      usage: `<span class="agentos-badge status-active">
  <span class="pulse-dot"></span> ACTIVE · 自主運作中
</span>`
    },
    {
      title: 'AgentOS Backlog Watermark Pill (專案卷軸水位膠囊)',
      desc: '呈現專案目前未消化的待辦卷軸水位。點擊可展開即時任務詳情或聚焦目標專案。',
      demo: (
        <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap' }}>
          <div style={{ display: 'inline-flex', alignItems: 'center', gap: '8px', padding: '6px 14px', background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: '12px', fontSize: '0.85rem' }}>
            <span>🏛️ Zeus Writer</span>
            <span style={{ padding: '2px 8px', borderRadius: '999px', background: 'rgba(239, 68, 68, 0.2)', border: '1px solid rgba(239, 68, 68, 0.5)', color: '#f87171', fontSize: '0.75rem', fontWeight: 700 }}>2 卷待辦</span>
          </div>
          <div style={{ display: 'inline-flex', alignItems: 'center', gap: '8px', padding: '6px 14px', background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: '12px', fontSize: '0.85rem' }}>
            <span>📺 YouTube AI</span>
            <span style={{ padding: '2px 8px', borderRadius: '999px', background: 'rgba(245, 158, 11, 0.2)', border: '1px solid rgba(245, 158, 11, 0.5)', color: '#fbbf24', fontSize: '0.75rem', fontWeight: 700 }}>1 卷待辦</span>
          </div>
          <div style={{ display: 'inline-flex', alignItems: 'center', gap: '8px', padding: '6px 14px', background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: '12px', fontSize: '0.85rem' }}>
            <span>🏰 AgentOS Core</span>
            <span style={{ padding: '2px 8px', borderRadius: '999px', background: 'rgba(16, 185, 129, 0.2)', border: '1px solid rgba(16, 185, 129, 0.5)', color: '#34d399', fontSize: '0.75rem', fontWeight: 700 }}>0 卷 (清空)</span>
          </div>
        </div>
      ),
      usage: `<div class="backlog-pill">
  <span>🏛️ Zeus Writer</span>
  <span class="scroll-tag">2 卷待辦</span>
</div>`
    },
    {
      title: 'AgentOS Incident Sentinel Banner (雙相哨兵警示列)',
      desc: '當巡檢哨兵發現異常（如 308 誤報、鏈接中斷、CI 失敗）時，自動推播至管理儀表板，支援人工或審核官覆核。',
      demo: (
        <div style={{ padding: '12px 18px', background: 'rgba(239, 68, 68, 0.1)', border: '1px solid rgba(239, 68, 68, 0.4)', borderRadius: '12px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <div style={{ color: '#f87171', fontWeight: 700, fontSize: '0.9rem' }}>🚨 哨兵巡檢告警：Zeus Writer 小說進度停滯</div>
            <div style={{ color: '#94a3b8', fontSize: '0.8rem', marginTop: '2px' }}>上次更新 6 個月前，已由審計銳爪審核為 CONFIRMED_DEFECT 並派案至待辦清單。</div>
          </div>
          <span style={{ padding: '4px 10px', background: 'rgba(239, 68, 68, 0.2)', border: '1px solid rgba(239, 68, 68, 0.6)', color: '#fca5a5', borderRadius: '8px', fontSize: '0.75rem', fontWeight: 700 }}>
            已入隊
          </span>
        </div>
      ),
      usage: `<div class="incident-banner incident-critical">
  <span>🚨 哨兵告警：[項目名稱]</span>
  <span class="incident-status">已入隊待審</span>
</div>`
    }
  ];

  return (
    <main style={{ minHeight: '100vh', padding: '3rem 1.5rem' }}>
      <div className="container" style={{ maxWidth: 960 }}>
        <button 
          className="btn btn-secondary" 
          onClick={() => router.push('/')} 
          style={{ marginBottom: '1.5rem', display: 'inline-flex', alignItems: 'center', gap: '6px' }}
        >
          ← Back to Dashboard
        </button>
        <p style={{ color: 'var(--color-text-muted)', letterSpacing: '0.12em', textTransform: 'uppercase', fontSize: '0.85rem' }}>AgentOS UI Design System</p>
        <h1 className="gradient-text" style={{ fontSize: '2.5rem', fontWeight: 800, marginBottom: '0.75rem' }}>可下載 UI 元件庫 (Component Vault)</h1>
        <p style={{ color: 'var(--color-text-secondary)', marginBottom: '2.5rem' }}>AgentOS 生態系經過實際生產環境驗證的介面元件，支援 Web Components 與 React。</p>

        <div style={{ display: 'grid', gap: '2rem' }}>
          {components.map((c, i) => (
            <section key={i} className="glass" style={{ padding: '1.75rem', borderRadius: '1rem', border: '1px solid rgba(255,255,255,0.08)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1rem', flexWrap: 'wrap', gap: '1rem' }}>
                <div>
                  <h2 style={{ fontSize: '1.25rem', fontWeight: 700, marginBottom: '0.35rem', color: '#f8fafc' }}>{c.title}</h2>
                  <p style={{ color: 'var(--color-text-secondary)', fontSize: '0.9rem' }}>{c.desc}</p>
                </div>
                {c.downloadUrl && (
                  <a className="btn btn-primary" style={{ fontSize: '0.8rem', padding: '6px 14px' }} href={c.downloadUrl} download>
                    📥 下載 Web Component
                  </a>
                )}
              </div>

              {/* Live Preview Box */}
              <div style={{ padding: '1.25rem', background: 'rgba(0,0,0,0.3)', borderRadius: '12px', border: '1px solid rgba(255,255,255,0.05)', marginBottom: '1rem' }}>
                <div style={{ fontSize: '0.75rem', color: '#64748b', marginBottom: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.08em' }}>實時渲染預覽 (Live Preview)</div>
                {c.demo}
              </div>

              {/* Code Snippet Box */}
              <div style={{ position: 'relative' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                  <span style={{ fontSize: '0.75rem', color: '#64748b' }}>整合代碼 (Integration Snippet)</span>
                  <button 
                    onClick={() => copyCode(c.usage, i)}
                    style={{ background: 'none', border: '1px solid rgba(255,255,255,0.2)', color: '#94a3b8', borderRadius: '6px', padding: '3px 8px', fontSize: '0.75rem', cursor: 'pointer' }}
                  >
                    {copiedIndex === i ? '✅ 已複製' : '📋 複製代碼'}
                  </button>
                </div>
                <pre style={{ margin: 0, padding: '1rem', background: 'rgba(0,0,0,0.5)', borderRadius: '8px', fontSize: '0.8rem', color: '#cbd5e1', overflowX: 'auto', fontFamily: 'monospace' }}>
                  {c.usage}
                </pre>
              </div>
            </section>
          ))}
        </div>
      </div>
    </main>
  );
}
