import type { Metadata } from 'next';
import Link from 'next/link';

export const metadata: Metadata = {
  title: '眾神與職責 | AgentOS',
  description: '認識 AgentOS 的執行、驗收、規格、治理與環境模型職責。',
  robots: { index: true, follow: true },
};

// Public allowlist drawn from .agent/roles/registry.yaml.
// Not a runtime-health or personnel roster. Deliberately no private receipts.
const roles = [
  { id:'core.root', name:'LeopardCat Root', type:'基礎', description:'提供所有 Agent 共用的真相邊界與治理原則。' },
  { id:'sector.weaver', name:'Weaver', type:'規格', description:'將目標收斂成規格、限制條件與驗收標準。' },
  { id:'sector.paw', name:'The Paw', type:'執行', description:'將獲授權的規格轉化為可驗證實作。' },
  { id:'sector.claw', name:'The Claw', type:'審查', description:'以品質與安全視角檢查實作與失敗模式。' },
  { id:'sector.whisperer', name:'Whisperer', type:'探索', description:'探索可能方向，將候選想法交由規格職責收斂。' },
  { id:'governance.spec_steward', name:'Spec Steward', type:'規格治理', description:'追蹤正式規格的負責人、證據與結案狀態。' },
  { id:'governance.keeper', name:'Constitution Keeper', type:'系統治理', description:'維護核心規則、角色契約與政策一致性。' },
  { id:'system.cartographer', name:'Cartographer', type:'環境模型', description:'維持環境資源資料與查證時效的區別。' },
] as const;

export default function PublicAgents() {
  return <main style={{maxWidth:1100,margin:'auto',padding:'3rem 1.5rem',lineHeight:1.8}}>
    <nav style={{display:'flex',gap:'1.5rem',flexWrap:'wrap'}} aria-label="AgentOS 公開導覽"><Link href="/about">系統介紹</Link><Link href="/agents">眾神與職責</Link><a href="https://studio.milkcat.org/personas/" rel="noopener">Studio 角色故事</a></nav>
    <header style={{padding:'3rem 0 2rem'}}><p style={{color:'#9bbcff'}}>AGENTOS · RESPONSIBILITY DIRECTORY</p><h1 style={{fontSize:'clamp(2rem,5vw,3.6rem)'}}>眾神與職責</h1><p>這裡介紹系統角色的設計責任，而非即時工作者名單、工作狀態或私人觀測。角色名稱及職責來自現行治理登記，並不表示該角色現在在線。</p></header>
    <section aria-label="公開系統職責" style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(230px,1fr))',gap:'1rem'}}>
    {roles.map(role=><article key={role.id} style={{padding:'1.25rem',border:'1px solid #334155',borderRadius:12}}>
      <p style={{color:'#9bbcff',fontSize:'.9rem'}}>{role.type}</p><h2 style={{fontSize:'1.35rem'}}>{role.name}</h2><p>{role.description}</p><small style={{color:'#94a3b8'}}>{role.id}</small>
    </article>)}
    </section>
    <p style={{marginTop:'2rem'}}>小說角色、公開生活、插畫與互動體驗留在 <a href="https://studio.milkcat.org/" rel="noopener">Milkcat Studio</a>。工作分派、審查紀錄及節點觀測需在具備獨立授權的管理端處理。</p>
  </main>;
}
