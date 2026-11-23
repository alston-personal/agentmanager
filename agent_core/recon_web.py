"""
Hermes Recon Radar & Pantheon Web Views
執掌: agentos.milkcat.org 官方情資雷達 (/recon) 與系統眾神殿 (/pantheon)
遵循 design-taste-frontend 抗 slop 標準 (Taste Skill 2.5.1)：
- 高資訊密度、等邊對齊 (Equal Edges)、真實數據注入
- 無廉價 AI 漸層/多餘陰影卡片，工匠級等寬資料版型與動態微互動
- 實時反映各神祇生命週期 (Cycle 數、在席狀態、正在處理任務、近期 10 筆處理履歷與結果)
"""

import json
from pathlib import Path
from typing import Any, Dict, List

AGENT_DATA_ROOT = Path("/home/ubuntu/agent-data")
RECON_LEDGER = AGENT_DATA_ROOT / "personas" / "sector-hermes" / "recon_ledger.json"
PERSONAS_DIR = AGENT_DATA_ROOT / "personas"


def get_recon_ledger_data() -> List[Dict[str, Any]]:
    if not RECON_LEDGER.exists():
        return []
    try:
        data = json.loads(RECON_LEDGER.read_text(encoding="utf-8"))
        # 兼容 records 與 ingested_weapons
        records = data.get("records")
        if records is not None and isinstance(records, list):
            return records
        return data.get("ingested_weapons", [])
    except Exception:
        return []


def get_god_runtime_state(slug: str) -> Dict[str, Any]:
    state_file = PERSONAS_DIR / slug / "pdca" / "state.json"
    if not state_file.exists():
        return {
            "cycle": 0,
            "status": "OFFLINE",
            "last_tick_at": "-",
            "current_task": "未啟動或未建置",
            "activities": []
        }
    try:
        data = json.loads(state_file.read_text(encoding="utf-8"))
        cycle = data.get("cycle", 0)
        status = data.get("status", "STANDBY")
        last_tick_at = data.get("last_tick_at", "-")
        activities = data.get("recent_activities", [])
        
        # 正在處理或最後處理的任務
        current_task = data.get("current_task") or data.get("active_goal")
        if not current_task and activities:
            current_task = activities[-1].get("task", "在席待命")
        elif not current_task:
            current_task = "在席待命"
            
        return {
            "cycle": cycle,
            "status": status,
            "last_tick_at": last_tick_at,
            "current_task": current_task,
            "activities": activities
        }
    except Exception:
        return {
            "cycle": 0,
            "status": "ERROR",
            "last_tick_at": "-",
            "current_task": "狀態讀取異常",
            "activities": []
        }


def render_recon_html() -> str:
    weapons = get_recon_ledger_data()
    
    rows = []
    if weapons:
        for w in weapons:
            name = w.get("name") or w.get("tool_name", "unknown")
            repo = w.get("target_repo") or w.get("repo", "")
            repo_display = repo.replace("https://github.com/", "")
            stars = w.get("stars")
            stars_badge = f"<span class=\"stat-stars\">★ {stars:,}</span>" if stars else ""
            category = w.get("category", "Tech")
            tier = w.get("tier", "入庫武器")
            summary = w.get("summary") or w.get("purpose", "")
            output_skill = w.get("output_skill", "-")
            status = w.get("status", "INGESTED")
            ts = (w.get("timestamp") or w.get("ingested_at") or "")[:10]
            
            rows.append(f"""
            <tr class="table-row">
              <td class="font-mono weapon-name">
                <div class="name-box">{name} {stars_badge}</div>
                <div class="repo-sub"><a href="{repo}" target="_blank" rel="noopener" class="link-mono">{repo_display} ↗</a></div>
              </td>
              <td><span class="badge badge-cat">{category}</span></td>
              <td><span class="badge badge-tier">{tier}</span></td>
              <td class="desc-cell">{summary}</td>
              <td class="font-mono text-xs text-muted">{output_skill}</td>
              <td><span class="badge badge-status">{status}</span></td>
              <td class="font-mono text-xs text-muted">{ts}</td>
            </tr>
            """)
    else:
        rows.append("""<tr><td colspan="7" class="empty-cell font-mono">情資雷達正在掃描中，尚無入庫武器紀錄。</td></tr>""")

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
  --bg: #07090e;
  --surface: #0e121a;
  --surface-hover: #141b26;
  --border: #1e2638;
  --border-light: #2a344d;
  --text: #f3f4f6;
  --text-muted: #8b9bb4;
  --primary: #38bdf8;
  --amber: #f59e0b;
  --emerald: #10b981;
  --indigo: #6366f1;
}}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
  background: var(--bg);
  color: var(--text);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  line-height: 1.5;
  padding: 40px 24px;
}}
.container {{ max-width: 1200px; margin: 0 auto; }}
.nav {{
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid var(--border);
  padding-bottom: 16px;
  margin-bottom: 32px;
}}
.logo {{ font-weight: 700; font-size: 16px; color: #fff; text-decoration: none; letter-spacing: -0.02em; }}
.nav-links {{ display: flex; gap: 20px; font-size: 13px; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }}
.nav-links a {{ color: var(--text-muted); text-decoration: none; transition: color 0.15s; }}
.nav-links a:hover, .nav-links a.active {{ color: #fff; }}
.hero {{ margin-bottom: 32px; }}
.hero-tag {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 11px; text-transform: uppercase; color: var(--emerald); letter-spacing: 0.08em; margin-bottom: 8px; }}
.hero h1 {{ font-size: 26px; font-weight: 700; letter-spacing: -0.03em; margin-bottom: 8px; color: #fff; }}
.hero p {{ color: var(--text-muted); font-size: 14px; max-width: 760px; }}
.card-table {{
  background: var(--surface);
  border: 1px solid var(--border);
  overflow-x: auto;
}}
table {{ width: 100%; border-collapse: collapse; text-align: left; font-size: 12px; }}
th {{
  background: #0a0d14;
  padding: 12px 14px;
  color: var(--text-muted);
  font-weight: 600;
  text-transform: uppercase;
  font-size: 11px;
  letter-spacing: 0.05em;
  border-bottom: 1px solid var(--border);
}}
td {{ padding: 14px; border-bottom: 1px solid var(--border); vertical-align: top; }}
.table-row:hover td {{ background: var(--surface-hover); }}
.font-mono {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }}
.text-muted {{ color: var(--text-muted); }}
.text-xs {{ font-size: 11px; }}
.weapon-name {{ font-weight: 600; color: #fff; }}
.name-box {{ display: flex; align-items: center; gap: 6px; }}
.stat-stars {{ font-size: 10px; background: rgba(245, 158, 11, 0.15); color: var(--amber); border: 1px solid rgba(245, 158, 11, 0.3); padding: 1px 5px; border-radius: 4px; }}
.repo-sub {{ margin-top: 4px; }}
.link-mono {{ color: var(--primary); text-decoration: none; font-size: 11px; }}
.link-mono:hover {{ text-decoration: underline; }}
.desc-cell {{ max-width: 380px; font-size: 12px; color: #d1d5db; line-height: 1.4; }}
.badge {{ display: inline-block; padding: 2px 6px; font-size: 10px; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; border-radius: 3px; font-weight: 500; }}
.badge-cat {{ background: rgba(56, 189, 248, 0.1); color: var(--primary); border: 1px solid rgba(56, 189, 248, 0.25); }}
.badge-tier {{ background: rgba(99, 102, 241, 0.1); color: #818cf8; border: 1px solid rgba(99, 102, 241, 0.25); }}
.badge-status {{ background: rgba(16, 185, 129, 0.1); color: var(--emerald); border: 1px solid rgba(16, 185, 129, 0.25); }}
.empty-cell {{ text-align: center; padding: 40px; color: var(--text-muted); }}
.footer {{ margin-top: 48px; border-top: 1px solid var(--border); padding-top: 16px; font-size: 12px; color: var(--text-muted); display: flex; justify-content: space-between; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }}
</style>
</head>
<body>
<div class="container">
  <div class="nav">
    <a href="/" class="logo">AGENTOS PLATFORM</a>
    <div class="nav-links">
      <a href="/welcome">STATUS</a>
      <a href="/pantheon">PANTHEON</a>
      <a href="/recon" class="active">RECON</a>
      <a href="https://studio.milkcat.org/" target="_blank" rel="noopener">STUDIO ↗</a>
    </div>
  </div>

  <div class="hero">
    <div class="hero-tag">AUTONOMOUS WEAPONRY INTAKE RADAR</div>
    <h1>📡 赫密士開源情資雷達與武器庫 (Hermes Recon)</h1>
    <p>執掌神祇 <code>sector.hermes</code>。負責全球前瞻開源技術探索、自動試毒評估，並將通過審查之頂尖武器引入全生態。</p>
  </div>

  <div class="card-table">
    <table>
      <thead>
        <tr>
          <th>武器/技能名稱與開源倉庫</th>
          <th>分類</th>
          <th>分流層級</th>
          <th>武器用途與核心價值</th>
          <th>落地技能 (SKILL)</th>
          <th>入庫狀態</th>
          <th>探勘時間</th>
        </tr>
      </thead>
      <tbody>
        {weapons_html}
      </tbody>
    </table>
  </div>

  <div class="footer">
    <div>ROLE: <code>sector.hermes</code> (HermesReconWorker)</div>
    <div>DATA SOURCE: Oracle Local Node (Truth)</div>
  </div>
</div>
</body>
</html>"""


def render_pantheon_html() -> str:
    gods = [
        {
            "name": "Atlas 阿特拉斯",
            "title": "擎天架構與任務閉環守護神",
            "role": "system-atlas",
            "focus": "全生態任務拆解、無孤兒注意力調度、死鎖解構與專案永續推進",
            "badge": "架構統籌",
            "color": "#06b6d4",
        },
        {
            "name": "The Paw 神爪",
            "title": "實體代碼落地建造神爪",
            "role": "the-paw",
            "focus": "實作落地 (Construct Phase)、驗收指令執行、STATUS.md 自動閉環標記",
            "badge": "首席工匠",
            "color": "#8b5cf6",
        },
        {
            "name": "The Claw 神鷹",
            "title": "紅線審計與質量守護神",
            "role": "the-claw",
            "focus": "PR 程式碼審查 (Review Phase)、安全漏洞攔截、防禦盲目覆寫",
            "badge": "法理審計",
            "color": "#ef4444",
        },
        {
            "name": "Hermes 赫密士",
            "title": "神使情資雷達與武器探勘",
            "role": "sector-hermes",
            "focus": "外部技術偵查 (`recon_ledger.json`)、開源技能消化、武器庫引進",
            "badge": "情報神使",
            "color": "#10b981",
        },
        {
            "name": "Themis 忒彌斯",
            "title": "正義法規與聖諭天平女神",
            "role": "governance-themis-command-steward",
            "focus": "全域專案島嶼時序差分 (`/project-diff`)、願景與架構契約防漂移審計",
            "badge": "天規法度",
            "color": "#f59e0b",
        },
        {
            "name": "Rhea 瑞亞",
            "title": "經驗繁衍與母神記憶",
            "role": "system-memory-archivist",
            "focus": "記憶宮殿蒸餾、LLM Wiki 永久化概念條目、經驗生長審計",
            "badge": "繁衍基石",
            "color": "#ec4899",
        },
        {
            "name": "Gateway 管家",
            "title": "分散式網關反向代理守衛",
            "role": "system-gateway-steward",
            "focus": "Nginx 反向代理配置、SSL/TLS 憑證維護、路由轉發與在席監控",
            "badge": "閘道守衛",
            "color": "#3b82f6",
        },
        {
            "name": "Sentinel 質量哨兵",
            "title": "全生態五維品質巡檢使",
            "role": "system-quality-sentinel",
            "focus": "自主巡查五維指標（小說產出、社群轉譯、幽靈專案、美學抗 slop、進程在席）",
            "badge": "質量哨兵",
            "color": "#ec4899",
        },
    ]

    cards = []
    for g in gods:
        st = get_god_runtime_state(g["role"])
        cycle = st["cycle"]
        status = st["status"]
        last_tick = st["last_tick_at"][:19].replace("T", " ")
        curr_task = st["current_task"]
        activities = st["activities"]

        # 歷程日誌列表 (最多 5 筆精簡展示)
        act_rows = []
        if activities:
            for act in reversed(activities[-5:]):
                v = act.get("verdict", "INFO")
                v_class = "pass" if v == "PASS" else ("fail" if v == "FAIL" else "info")
                ts = act.get("timestamp", "")[:19].replace("T", " ")
                t_desc = act.get("task", "")
                c_num = act.get("cycle", "-")
                act_rows.append(f"""
                <div class="act-row">
                  <div class="act-header font-mono">
                    <span class="act-cycle">C{c_num}</span>
                    <span class="act-verdict {v_class}">[{v}]</span>
                    <span class="act-time">{ts}</span>
                  </div>
                  <div class="act-desc">{t_desc}</div>
                </div>
                """)
        else:
            act_rows.append("""<div class="act-empty font-mono">尚無近期履歷</div>""")

        act_html = "\n".join(act_rows)

        cards.append(f"""
        <div class="god-panel" style="border-top: 2px solid {g['color']};">
          <div class="panel-header">
            <div>
              <div class="god-name">{g['name']}</div>
              <div class="god-title font-mono">{g['title']}</div>
            </div>
            <div class="header-right font-mono">
              <span class="badge-role" style="color: {g['color']};">{g['badge']}</span>
              <span class="badge-status {status.lower()}">{status}</span>
            </div>
          </div>

          <div class="stat-grid font-mono">
            <div class="stat-item">
              <div class="stat-label">CYCLE</div>
              <div class="stat-val">{cycle}</div>
            </div>
            <div class="stat-item">
              <div class="stat-label">LAST TICK</div>
              <div class="stat-val text-xs">{last_tick}</div>
            </div>
          </div>

          <div class="section-box">
            <div class="section-title font-mono">▸ 職掌與核心使命</div>
            <div class="section-text">{g['focus']}</div>
          </div>

          <div class="section-box active-task-box">
            <div class="section-title font-mono">▸ 當前處理 / 在席任務</div>
            <div class="section-text active-task font-mono">{curr_task}</div>
          </div>

          <div class="history-box">
            <div class="section-title font-mono">▸ 近期執行履歷 (PDCA State)</div>
            <div class="history-list">
              {act_html}
            </div>
          </div>
        </div>
        """)

    cards_html = "\n".join(cards)

    return f"""<!doctype html>
<html lang="zh-TW">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AgentOS Pantheon · 系統眾神殿與在席監控</title>
<meta name="description" content="AgentOS 核心工程與治理守護神祇名冊、實時 Cycle 執行狀態與歷史處理日誌。">
<style>
:root {{
  --bg: #07090e;
  --surface: #0e121a;
  --surface-alt: #131822;
  --border: #1e2638;
  --text: #f3f4f6;
  --text-muted: #8b9bb4;
  --primary: #38bdf8;
  --emerald: #10b981;
  --rose: #f43f5e;
  --amber: #f59e0b;
}}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
  background: var(--bg);
  color: var(--text);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  line-height: 1.5;
  padding: 40px 24px;
}}
.container {{ max-width: 1300px; margin: 0 auto; }}
.nav {{
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid var(--border);
  padding-bottom: 16px;
  margin-bottom: 32px;
}}
.logo {{ font-weight: 700; font-size: 16px; color: #fff; text-decoration: none; letter-spacing: -0.02em; }}
.nav-links {{ display: flex; gap: 20px; font-size: 13px; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }}
.nav-links a {{ color: var(--text-muted); text-decoration: none; transition: color 0.15s; }}
.nav-links a:hover, .nav-links a.active {{ color: #fff; }}
.hero {{ margin-bottom: 32px; }}
.hero-tag {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 11px; text-transform: uppercase; color: var(--primary); letter-spacing: 0.08em; margin-bottom: 8px; }}
.hero h1 {{ font-size: 26px; font-weight: 700; letter-spacing: -0.03em; margin-bottom: 8px; color: #fff; }}
.hero p {{ color: var(--text-muted); font-size: 14px; max-width: 800px; }}
.grid {{
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(380px, 1fr));
  gap: 20px;
}}
.god-panel {{
  background: var(--surface);
  border: 1px solid var(--border);
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}}
.god-panel:hover {{ border-color: #2e3a55; }}
.panel-header {{ display: flex; justify-content: space-between; align-items: flex-start; }}
.god-name {{ font-size: 18px; font-weight: 700; color: #fff; letter-spacing: -0.02em; }}
.god-title {{ font-size: 11px; color: var(--text-muted); margin-top: 2px; }}
.header-right {{ display: flex; flex-direction: column; align-items: flex-end; gap: 4px; }}
.badge-role {{ font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; }}
.badge-status {{ font-size: 10px; padding: 1px 6px; border-radius: 3px; font-weight: 600; }}
.badge-status.running {{ background: rgba(16, 185, 129, 0.15); color: var(--emerald); border: 1px solid rgba(16, 185, 129, 0.3); }}
.badge-status.standby {{ background: rgba(245, 158, 11, 0.15); color: var(--amber); border: 1px solid rgba(245, 158, 11, 0.3); }}
.badge-status.offline {{ background: rgba(244, 63, 94, 0.15); color: var(--rose); border: 1px solid rgba(244, 63, 94, 0.3); }}
.stat-grid {{ display: grid; grid-template-columns: 1fr 2fr; gap: 8px; background: var(--surface-alt); padding: 10px 12px; border: 1px solid var(--border); }}
.stat-item {{ display: flex; flex-direction: column; }}
.stat-label {{ font-size: 10px; color: var(--text-muted); letter-spacing: 0.05em; }}
.stat-val {{ font-size: 13px; font-weight: 600; color: #fff; }}
.stat-val.text-xs {{ font-size: 11px; color: #cbd5e1; }}
.section-box {{ display: flex; flex-direction: column; gap: 4px; }}
.section-title {{ font-size: 10px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.05em; }}
.section-text {{ font-size: 12px; color: #cbd5e1; line-height: 1.45; }}
.active-task-box {{ background: rgba(56, 189, 248, 0.04); border: 1px solid rgba(56, 189, 248, 0.15); padding: 10px; }}
.active-task {{ color: var(--primary); font-size: 11px; word-break: break-all; }}
.history-box {{ display: flex; flex-direction: column; gap: 8px; border-top: 1px solid var(--border); padding-top: 12px; }}
.history-list {{ display: flex; flex-direction: column; gap: 8px; max-height: 220px; overflow-y: auto; }}
.act-row {{ background: var(--surface-alt); border: 1px solid var(--border); padding: 8px 10px; }}
.act-header {{ display: flex; align-items: center; gap: 6px; font-size: 10px; margin-bottom: 4px; }}
.act-cycle {{ color: var(--primary); font-weight: 600; }}
.act-verdict.pass {{ color: var(--emerald); font-weight: 600; }}
.act-verdict.fail {{ color: var(--rose); font-weight: 600; }}
.act-verdict.info {{ color: var(--amber); font-weight: 600; }}
.act-time {{ color: var(--text-muted); margin-left: auto; }}
.act-desc {{ font-size: 11px; color: #e2e8f0; line-height: 1.35; }}
.act-empty {{ color: var(--text-muted); font-size: 11px; padding: 12px; text-align: center; }}
.font-mono {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }}
.footer {{ margin-top: 48px; border-top: 1px solid var(--border); padding-top: 16px; font-size: 12px; color: var(--text-muted); display: flex; justify-content: space-between; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }}
</style>
</head>
<body>
<div class="container">
  <div class="nav">
    <a href="/" class="logo">AGENTOS PLATFORM</a>
    <div class="nav-links">
      <a href="/welcome">STATUS</a>
      <a href="/pantheon" class="active">PANTHEON</a>
      <a href="/recon">RECON</a>
      <a href="https://studio.milkcat.org/personas/" target="_blank" rel="noopener">PERSONAS ↗</a>
      <a href="https://studio.milkcat.org/" target="_blank" rel="noopener">STUDIO ↗</a>
    </div>
  </div>

  <div class="hero">
    <div class="hero-tag">DISTRIBUTED AUTONOMOUS GOVERNANCE & ENGINEERING MESH</div>
    <h1>🏛️ AgentOS 眾神殿與神祇實時在席監控 (The Pantheon)</h1>
    <p>全系統核心工程、治理與偵查神祇矩陣。即時反映各神祇之自主演進生命週期 (Cycle)、心跳狀態、當前任務與 PDCA 執行履歷。</p>
  </div>

  <div class="grid">
    {cards_html}
  </div>

  <div class="footer">
    <div>CENTRAL GOVERNANCE: AgentOS Constitutional Council</div>
    <div>TELEMETRY: Live Node PDCA State</div>
  </div>
</div>
</body>
</html>"""
