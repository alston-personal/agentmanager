import type { Metadata } from 'next';
import Link from 'next/link';

export const metadata: Metadata = {
  title: 'AgentOS | 系統介紹',
  description: 'AgentOS 是以持久工作狀態、治理、能力解析與可驗證執行為核心的 AI Agent 系統。',
  robots: { index: true, follow: true },
};

const capabilities = [
  { title: '持續接手', detail: '將任務脈絡與狀態保存在模型與對話之外，降低更換執行者時的重建成本。' },
  { title: '角色與治理', detail: '透過職責、授權與審查規範管理執行，能力存在不代表可以任意操作。' },
  { title: '跨節點工作', detail: '透過節點登記、能力查詢、派工與回執銜接不同主機上的執行者。' },
  { title: '可查證完成', detail: '以測試、執行回執與正式驗收區分候選實作、已測試能力和正式運行狀態。' },
];

export default function AgentOSAbout() {
  return <main style={{maxWidth:1050,margin:'auto',padding:'3rem 1.5rem',lineHeight:1.8}}>
    <nav aria-label="AgentOS 公開導覽" style={{display:'flex',gap:'1.5rem',flexWrap:'wrap'}}>
      <Link href="/about">系統介紹</Link><Link href="/agents">眾神與職責</Link>
      <a href="https://studio.milkcat.org/" rel="noopener">探索 Milkcat Studio</a>
    </nav>
    <header style={{padding:'4rem 0 2rem'}}>
      <p style={{color:'#9bbcff'}}>AGENTOS · PUBLIC INTRODUCTION</p>
      <h1 style={{fontSize:'clamp(2rem,5vw,4rem)',lineHeight:1.2}}>讓工作延續，而不受限於單一模型或裝置</h1>
      <p style={{fontSize:'1.15rem',maxWidth:750}}>AgentOS 以持久化工作狀態、治理規則、角色責任與執行回執，串接 AI Agents 與節點。這裡介紹系統如何設計；私人任務、登入資訊、執行日誌與操作控制不在公開頁面呈現。</p>
    </header>
    <section aria-labelledby="capabilities"><h2 id="capabilities">核心能力</h2>
      <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(220px,1fr))',gap:'1rem'}}>
        {capabilities.map(item=><article key={item.title} style={{padding:'1.25rem',border:'1px solid #334155',borderRadius:12}}><h3>{item.title}</h3><p>{item.detail}</p></article>)}
      </div>
    </section>
    <section style={{marginTop:'3rem'}}><h2>實作成熟度</h2><p>系統具備可測試的持久協作、治理與節點能力；特定模型切換、正式部署健康與完整自主閉環仍須以各自的最新驗收回執證明。本頁不把開發候選誤當成已上線功能。</p>
      <p><Link href="/agents">認識角色、職責與協作方式 →</Link></p>
    </section>
  </main>;
}
