"""
Hermes Recon Radar & Pantheon Web Views
執掌: agentos.milkcat.org 官方情資雷達 (/recon) 與系統眾神殿 (/pantheon)
遵循 design-taste-frontend 抗 slop 標準，簡約科技極簡、高資訊密度、乾淨深色排版。
"""

import json
from pathlib import Path
from typing import Any, Dict, List

AGENT_DATA_ROOT = Path("/home/ubuntu/agent-data")
RECON_LEDGER = AGENT_DATA_ROOT / "personas" / "sector-hermes" / "recon_ledger.json"


def get_recon_ledger_data() -> List[Dict[str, Any]]:
    if not RECON_LEDGER.exists():
        return []
    try:
        data = json.loads(RECON_LEDGER.read_text(encoding="utf-8"))
        return data.get("ingested_weapons", [])
    except Exception:
        return []


def render_recon_html() -> str:
    weapons = get_recon_ledger_data()
    
    rows = []
    if weapons:
        for w in weapons:
            rows.append(f"""
            <tr>
              <td class="font-mono text-amber">{w.get('tool_name', 'unknown')}</td>
              <td><a href="https://github.com/{w.get('repo', '')}" target="_blank" rel="noopener" class="link">{w.get('repo', '')}</a></td>
              <td><span class="badge badge-tech">{w.get('category', 'tech')}</span></td>
              <td class="text-dim">{w.get('target_role', 'all')}</td>
              <td class="text-sm">{w.get('purpose', '')}</td>
              <td class="font-mono text-xs">{w.get('ingested_at', '')[:10]}</td>
            </tr>
            """)
    else:
        rows.append("""<tr><td colspan="6" class="text-center text-dim py-8">情資雷達正在掃描中，尚無入庫武器紀錄。</td></tr>""")

    weapons_html = "\n".join(rows)

    return f"""<!doctype html>
<html lang="zh-TW">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Hermes Recon Radar · AgentOS 開源情資雷達與武器庫</title>
<meta name="description" content="AgentOS 外部前瞻技術探勘、開源武器庫入庫日誌與自治評估雷達。">
<style>
:root {{
  --bg: #090d16;
  --surface: #101726;
  --border: rgba(255, 255, 255, 0.08);
  --text: #f1f5f9;
  --text-dim: #94a3b8;
  --primary: #38bdf8;
  --amber: #f59e0b;
  --emerald: #10b981;
}}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
  background: var(--bg);
  color: var(--text);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  line-height: 1.6;
  padding: 32px 20px;
}}
.container {{ max-width: 1080px; margin: 0 auto; }}
.nav {{
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid var(--border);
  padding-bottom: 16px;
  margin-bottom: 32px;
}}
.logo {{ font-weight: 700; font-size: 18px; color: #fff; text-decoration: none; }}
.nav-links {{ display: flex; gap: 16px; font-size: 14px; }}
.nav-links a {{ color: var(--text-dim); text-decoration: none; transition: color 0.15s; }}
.nav-links a:hover, .nav-links a.active {{ color: #fff; }}
.hero {{ margin-bottom: 36px; }}
.hero h1 {{ font-size: 28px; font-weight: 700; margin-bottom: 8px; }}
.hero p {{ color: var(--text-dim); font-size: 15px; max-width: 640px; }}
.card {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  overflow: hidden;
}}
table {{ width: 100%; border-collapse: collapse; text-align: left; font-size: 13px; }}
th {{
  background: rgba(255, 255, 255, 0.03);
  padding: 12px 16px;
  color: var(--text-dim);
  font-weight: 500;
  border-bottom: 1px solid var(--border);
}}
td {{ padding: 14px 16px; border-bottom: 1px solid var(--border); }}
tr:last-child td {{ border-bottom: none; }}
.font-mono {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }}
.text-amber {{ color: var(--amber); }}
.text-dim {{ color: var(--text-dim); }}
.text-xs {{ font-size: 11px; }}
.text-sm {{ font-size: 12px; }}
.link {{ color: var(--primary); text-decoration: none; }}
.link:hover {{ text-decoration: underline; }}
.badge {{
  display: inline-block;
  padding: 2px 8px;
  border-radius: 9999px;
  font-size: 11px;
  font-weight: 500;
}}
.badge-tech {{ background: rgba(56, 189, 248, 0.15); color: #38bdf8; border: 1px solid rgba(56, 189, 248, 0.25); }}
.footer {{ margin-top: 48px; border-top: 1px solid var(--border); padding-top: 16px; font-size: 12px; color: var(--text-dim); display: flex; justify-content: space-between; }}
</style>
</head>
<body>
<div class="container">
  <div class="nav">
    <a href="/" class="logo">⚙️ AgentOS Platform</a>
    <div class="nav-links">
      <a href="/welcome">狀態 (Status)</a>
      <a href="/pantheon">眾神殿 (Pantheon)</a>
      <a href="/recon" class="active">情資雷達 (Recon)</a>
      <a href="https://studio.milkcat.org/" target="_blank" rel="noopener">創作工坊 (Studio ↗)</a>
    </div>
  </div>

  <div class="hero">
    <h1>📡 赫密士開源情資雷達與武器庫 (Hermes Recon Radar)</h1>
    <p>執掌神祇 <code>sector.hermes</code> (神使偵察兵)。負責全球前瞻開源技術探索、自動試毒評估，並將通過審查之頂尖武器引進全生態。</p>
  </div>

  <div class="card">
    <table>
      <thead>
        <tr>
          <th>武器/技能名稱</th>
          <th>開源倉庫 (Source)</th>
          <th>分類</th>
          <th>指定執行角色</th>
          <th>武器用途與核心價值</th>
          <th>入庫時間</th>
        </tr>
      </thead>
      <tbody>
        {weapons_html}
      </tbody>
    </table>
  </div>

  <div class="footer">
    <div>執掌守衛: <code>HermesReconWorker</code> · 遵循 AgentOS 憲法架構</div>
    <div>真實真相: Oracle Local Node</div>
  </div>
</div>
</body>
</html>"""


def render_pantheon_html() -> str:
    gods = [
        {
            "name": "Atlas 阿特拉斯",
            "title": "擎天架構與閉環規劃神祇",
            "role": "sector.atlas",
            "focus": "全生態任務拆解、無孤兒注意力流轉 (`attention_queue.json`)、防止專案停滯",
            "badge": "架構統籌",
            "color": "#06b6d4",
        },
        {
            "name": "The Paw 神爪",
            "title": "實體代碼落地建造神爪",
            "role": "sector.paw",
            "focus": "實作落地 (Construct Phase)、驗收指令執行、STATUS.md 自動閉環標記",
            "badge": "首席工匠",
            "color": "#8b5cf6",
        },
        {
            "name": "The Claw 神鷹",
            "title": "紅線審計與質量守護爪",
            "role": "sector.claw",
            "focus": "PR 程式碼審查 (Review Phase)、安全漏洞攔截、防禦盲目覆寫",
            "badge": "法理審計",
            "color": "#ef4444",
        },
        {
            "name": "Hermes 赫密士",
            "title": "神使情資雷達與開源武器探勘",
            "role": "sector.hermes",
            "focus": "外部技術偵查 (`recon_ledger.json`)、開源技能消化、武器庫引進",
            "badge": "情報神使",
            "color": "#10b981",
        },
        {
            "name": "Themis 忒彌斯",
            "title": "正義法規與聖諭天平女神",
            "role": "governance.themis_command_steward",
            "focus": "全域專案島嶼時序差分 (`/status-diff`, `/project-diff`)、願景契約合規審查",
            "badge": "天規法度",
            "color": "#f59e0b",
        },
        {
            "name": "Rhea 瑞亞",
            "title": "經驗繁衍與母神記憶",
            "role": "sector.rhea",
            "focus": "記憶宮殿蒸餾、LLM Wiki 永久化概念條目、經驗生長審計",
            "badge": "繁衍基石",
            "color": "#ec4899",
        },
    ]

    cards = []
    for g in gods:
        cards.append(f"""
        <div class="god-card" style="border-top: 3px solid {g['color']};">
          <div class="god-header">
            <h3>{g['name']}</h3>
            <span class="badge" style="background: rgba(255,255,255,0.08); color: {g['color']};">{g['badge']}</span>
          </div>
          <div class="god-role font-mono">{g['role']}</div>
          <div class="god-title">{g['title']}</div>
          <p class="god-desc">{g['focus']}</p>
        </div>
        """)

    cards_html = "\n".join(cards)

    return f"""<!doctype html>
<html lang="zh-TW">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AgentOS Pantheon · 系統眾神殿</title>
<meta name="description" content="AgentOS 核心工程與治理守護神祇名冊。">
<style>
:root {{
  --bg: #090d16;
  --surface: #101726;
  --border: rgba(255, 255, 255, 0.08);
  --text: #f1f5f9;
  --text-dim: #94a3b8;
  --primary: #38bdf8;
}}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
  background: var(--bg);
  color: var(--text);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  line-height: 1.6;
  padding: 32px 20px;
}}
.container {{ max-width: 1080px; margin: 0 auto; }}
.nav {{
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid var(--border);
  padding-bottom: 16px;
  margin-bottom: 32px;
}}
.logo {{ font-weight: 700; font-size: 18px; color: #fff; text-decoration: none; }}
.nav-links {{ display: flex; gap: 16px; font-size: 14px; }}
.nav-links a {{ color: var(--text-dim); text-decoration: none; transition: color 0.15s; }}
.nav-links a:hover, .nav-links a.active {{ color: #fff; }}
.hero {{ margin-bottom: 36px; }}
.hero h1 {{ font-size: 28px; font-weight: 700; margin-bottom: 8px; }}
.hero p {{ color: var(--text-dim); font-size: 15px; max-width: 720px; }}
.grid {{
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 20px;
}}
.god-card {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}}
.god-header {{ display: flex; justify-content: space-between; align-items: center; }}
.god-header h3 {{ font-size: 18px; font-weight: 700; color: #fff; }}
.god-role {{ font-size: 12px; color: var(--primary); }}
.god-title {{ font-size: 13px; color: #cbd5e1; font-weight: 500; }}
.god-desc {{ font-size: 13px; color: var(--text-dim); line-height: 1.5; }}
.font-mono {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }}
.badge {{
  display: inline-block;
  padding: 2px 8px;
  border-radius: 9999px;
  font-size: 11px;
  font-weight: 500;
}}
.link-box {{
  margin-top: 40px;
  padding: 20px 24px;
  background: rgba(56, 189, 248, 0.05);
  border: 1px solid rgba(56, 189, 248, 0.2);
  border-radius: 12px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}}
.link-box a {{
  color: var(--primary);
  text-decoration: none;
  font-weight: 600;
  font-size: 14px;
}}
.link-box a:hover {{ text-decoration: underline; }}
.footer {{ margin-top: 48px; border-top: 1px solid var(--border); padding-top: 16px; font-size: 12px; color: var(--text-dim); display: flex; justify-content: space-between; }}
</style>
</head>
<body>
<div class="container">
  <div class="nav">
    <a href="/" class="logo">⚙️ AgentOS Platform</a>
    <div class="nav-links">
      <a href="/welcome">狀態 (Status)</a>
      <a href="/pantheon" class="active">眾神殿 (Pantheon)</a>
      <a href="/recon">情資雷達 (Recon)</a>
      <a href="https://studio.milkcat.org/" target="_blank" rel="noopener">創作工坊 (Studio ↗)</a>
    </div>
  </div>

  <div class="hero">
    <h1>🏛️ AgentOS 系統眾神殿 (System Pantheon)</h1>
    <p>負責支撐 AgentOS 63 座專案島嶼、物理封鎖線與自主演進的核心工程神祇名冊。各神祇遵照嚴密之 PDCA 職責分工與憲法紅線守衛。</p>
  </div>

  <div class="grid">
    {cards_html}
  </div>

  <div class="link-box">
    <div>
      <h4 style="color:#fff; margin-bottom:4px;">🎨 尋找文學創作與故事 IP 角色？</h4>
      <p style="color:var(--text-dim); font-size:13px; margin:0;">澪 (Mio)、蒼玄、阿賴耶識、石虎掌門等創作品牌請前往 Studio。</p>
    </div>
    <a href="https://studio.milkcat.org/personas/" target="_blank" rel="noopener">前往 Studio 角色殿堂 ↗</a>
  </div>

  <div class="footer">
    <div>體制架構: <code>AgentOS Core Governance</code> · 6 大守護神祇實體</div>
    <div>身心合一: Zero False Completion Verified</div>
  </div>
</div>
</body>
</html>"""
