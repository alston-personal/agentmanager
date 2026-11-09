#!/usr/bin/env python3
"""AgentOS Universal Persona Portal Synchronizer.

Generates public persona observer dashboards and the central Persona Hub
under /home/ubuntu/zeus-writer/website/dist/personas/
Embeds the Universal Global Header to guarantee full cross-linking with zero dead ends.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

AGENTMANAGER_ROOT = Path("/home/ubuntu/agentmanager")
DATA_ROOT = Path("/home/ubuntu/agent-data")
DIST_PERSONAS = Path("/home/ubuntu/zeus-writer/website/dist/personas")
PUBLIC_PERSONAS = Path("/home/ubuntu/zeus-writer/website/public/personas")

PERSONA_MAPPINGS = [
    {
        "slug": "the-paw",
        "agent_id": "persona.engineering.paw",
        "name": "The Paw (工匠貓爪)",
        "domain": "系統工程",
        "domain_icon": "🛠️",
        "badge_color": "#38bdf8",
        "data_dir": DATA_ROOT / "personas/the-paw",
        "project_url": "/mission-control/",
        "project_label": "AgentOS 核心專案"
    },
    {
        "slug": "the-claw",
        "agent_id": "persona.security.claw",
        "name": "The Claw (鋼鐵利爪)",
        "domain": "安全審查",
        "domain_icon": "🛡️",
        "badge_color": "#f87171",
        "data_dir": DATA_ROOT / "personas/the-claw",
        "project_url": "/mission-control/",
        "project_label": "MetaShield 安全堡壘"
    },
    {
        "slug": "mio",
        "agent_id": "persona.mio",
        "name": "澪 / Mio",
        "domain": "社群實驗",
        "domain_icon": "🌸",
        "badge_color": "#cabdff",
        "data_dir": DATA_ROOT / "personas/sunlake-milkcat",
        "project_url": "/mio-room/",
        "project_label": "晴湖小築 (2.5D 私人空間)"
    },
    {
        "slug": "oursong",
        "agent_id": "persona.oursong_alstonhuang",
        "name": "OurSong Alston",
        "domain": "音樂數位資產",
        "domain_icon": "🎵",
        "badge_color": "#a7f3d0",
        "data_dir": DATA_ROOT / "personas/oursong_alstonhuang",
        "project_url": "https://www.oursong.com",
        "project_label": "OurSong 平台"
    },
    {
        "slug": "puma-shen",
        "agent_id": "persona.tarot.puma_shen",
        "name": "洋流大師・沈伯洋",
        "domain": "政策智囊・塔羅",
        "domain_icon": "🌊",
        "badge_color": "#818cf8",
        "data_dir": DATA_ROOT / "personas/puma-shen",
        "project_url": "https://leopardcat-tarot.milkcat.org/?persona=ocean-master",
        "project_label": "石虎塔羅・洋流解牌"
    },
    {
        "slug": "leopardcat",
        "agent_id": "persona.tarot.master",
        "name": "石虎掌門",
        "domain": "神秘學・塔羅",
        "domain_icon": "🐾",
        "badge_color": "#fbbf24",
        "data_dir": DATA_ROOT / "personas/leopardcat-master",
        "project_url": "https://leopardcat-tarot.milkcat.org/",
        "project_label": "石虎塔羅神殿"
    },
    {
        "slug": "tiandao-alaya",
        "agent_id": "persona.writer.tiandao_alaya",
        "name": "阿賴耶識",
        "domain": "長卷小說創作",
        "domain_icon": "📜",
        "badge_color": "#c084fc",
        "data_dir": DATA_ROOT / "personas/tiandao-alaya",
        "project_url": "/tiandao/",
        "project_label": "《天道敕令》小說連載"
    },
    {
        "slug": "tiandao-cangxuan",
        "agent_id": "persona.editor.tiandao_cangxuan",
        "name": "蒼玄主編",
        "domain": "文學審查・節律調控",
        "domain_icon": "⚖️",
        "badge_color": "#38bdf8",
        "data_dir": DATA_ROOT / "personas/tiandao-cangxuan",
        "project_url": "/tiandao/",
        "project_label": "天道編輯部"
    },
    {
        "slug": "tiandao-geek",
        "agent_id": "persona.lore.tiandao_geek",
        "name": "天道極客",
        "domain": "修真技術設定・架構注釋",
        "domain_icon": "💻",
        "badge_color": "#4ade80",
        "data_dir": DATA_ROOT / "personas/tiandao-geek",
        "project_url": "/tiandao/",
        "project_label": "經緯算閣注釋庫"
    },
]

GLOBAL_NAV_HTML = """
<header class="univ-header">
  <div class="univ-brand">
    <a href="/" target="_top">🐈‍⬛ <strong>Milkcat Studio</strong></a>
    <span class="univ-tag">AgentOS</span>
  </div>
  <nav class="univ-nav">
    <a href="/" target="_top">🏠 首頁</a>
    <a href="/mission-control/" target="_top">🛰️ 作戰指揮室</a>
    <a href="/role-island/" target="_top">🪐 3D 群島</a>
    <a href="/personas/" target="_top" class="active">👤 AI 角色神殿</a>
    <a href="/mio-room/" target="_top">🌸 晴湖小築 (Mio)</a>
    <a href="/tiandao/" target="_top">📖 《天道敕令》連載</a>
  </nav>
</header>
<style>
.univ-header {
  position: sticky; top: 0; left: 0; right: 0; z-index: 1000;
  background: rgba(9, 13, 22, 0.94);
  backdrop-filter: blur(14px); -webkit-backdrop-filter: blur(14px);
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  padding: 0.75rem 1.75rem;
  display: flex; justify-content: space-between; align-items: center;
  flex-wrap: wrap; gap: 0.75rem;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "PingFang TC", sans-serif;
  box-sizing: border-box;
}
.univ-brand a {
  color: #fff; text-decoration: none; font-size: 1.1rem; font-weight: 700;
  display: flex; align-items: center; gap: 8px;
}
.univ-tag {
  font-size: 0.7rem; background: rgba(56, 189, 248, 0.15); color: #38bdf8;
  padding: 2px 7px; border-radius: 4px; font-weight: 600;
}
.univ-nav { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.univ-nav a {
  color: #94a3b8; text-decoration: none; font-size: 0.85rem; font-weight: 500;
  padding: 0.35rem 0.75rem; border-radius: 6px; transition: all 0.2s;
  border: 1px solid transparent;
}
.univ-nav a:hover {
  color: #f1f5f9; background: rgba(255, 255, 255, 0.06);
  border-color: rgba(255, 255, 255, 0.1);
}
.univ-nav a.active {
  color: #38bdf8; background: rgba(56, 189, 248, 0.12);
  border-color: rgba(56, 189, 248, 0.3);
}
</style>
"""


def load_json(p: Path) -> dict[str, Any]:
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def load_events(p: Path) -> list[dict[str, Any]]:
    if not p.exists():
        return []
    events = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except Exception:
            continue
    return events


def generate_activity_json(p_cfg: dict[str, Any]) -> dict[str, Any]:
    data_dir: Path = p_cfg["data_dir"]
    core = load_json(data_dir / "character_core.json")
    state = load_json(data_dir / "persona_state.json")
    events = load_events(data_dir / "events/events.jsonl")

    voice = state.get("voice", {})
    pos = state.get("current_positioning", {})

    recent_items = []
    for ev in reversed(events):
        summary = ev.get("summary") or ev.get("payload", {}).get("message") or ev.get("type", "")
        recent_items.append({
            "time_label": ev.get("timestamp", "").replace("T", " ").replace("Z", " UTC"),
            "title": ev.get("type", "event").upper(),
            "summary": summary,
            "focus_label": ev.get("type", "action"),
            "event_id": ev.get("event_id", "")
        })

    return {
        "schema": "agentos.persona-observer-public/v1",
        "character_id": core.get("character_id", p_cfg["slug"]),
        "agent_id": p_cfg["agent_id"],
        "display_name": p_cfg["name"],
        "domain": p_cfg["domain"],
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "updated_label": "即時同步中",
        "activity_count": len(events),
        "energy": state.get("energy", {}).get("current", 85),
        "current": {
            "title": pos.get("identity") or core.get("mission", "自主運作中"),
            "summary": pos.get("current_focus") or pos.get("current_status") or "維持日常自主工作循環",
            "focus_label": p_cfg["domain"],
        },
        "voice": voice,
        "health": {
            "persona.core": "healthy",
            "persona.state": "healthy",
            "agentos.runtime": "healthy",
        },
        "recent": recent_items
    }


def render_persona_page(p_cfg: dict[str, Any], activity: dict[str, Any]) -> str:
    core = load_json(p_cfg["data_dir"] / "character_core.json")
    immutable_traits = core.get("immutable_traits", {})
    values = immutable_traits.get("values", [])
    forbidden = immutable_traits.get("forbidden", [])
    mission = core.get("mission", "")

    recent_html = "".join([
        f'<article class="card"><div class="row"><div><strong style="color:#e2e8f0;">{ev.get("time_label", "")} · {ev.get("title", "")}</strong><div style="margin-top:6px;color:#94a3b8;line-height:1.6;">{ev.get("summary", "")}</div></div><span class="tag">{ev.get("focus_label", "")}</span></div></article>'
        for ev in activity.get("recent", [])
    ]) or '<div class="muted">尚無近期公開事件記錄</div>'

    values_html = "".join([f'<span class="badge">{v}</span>' for v in values])
    forbidden_html = "".join([f'<li>{f}</li>' for f in forbidden])

    special_banner = ""
    if p_cfg["slug"] == "mio":
        special_banner = """
        <div style="margin: 20px 0; padding: 20px 24px; background: rgba(56, 189, 248, 0.08); border: 1px solid rgba(56, 189, 248, 0.25); border-radius: 14px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 14px;">
          <div>
            <div style="font-weight: 700; color: #fff; font-size: 16px;">🌸 澪的晴湖小築 (Cozy Haven) 2.5D 私人空間已開放</div>
            <div style="color: #94a3b8; font-size: 13px; margin-top: 4px;">內含：走入式衣櫥 (Tryon 換裝)、靈感創作桌 (Threads 草稿)、充電睡眠床與晴湖全景落地窗。</div>
          </div>
          <a href="/mio-room/" style="background: #38bdf8; color: #090d16; font-weight: 700; font-size: 14px; padding: 8px 18px; border-radius: 8px; text-decoration: none; transition: 0.2s;">走入晴湖小築房間 →</a>
        </div>
        """

    return f"""<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{p_cfg["name"]} ｜ AgentOS 角色觀測窗</title>
<style>
:root {{
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "PingFang TC", "Noto Sans TC", sans-serif;
  color: #f1f5f9;
  background: #090d16;
}}
body {{ margin: 0; padding: 0; min-height: 100vh; }}
.wrap {{ max-width: 900px; margin: auto; padding: 24px 20px 80px; }}
.nav-breadcrumbs {{ margin-bottom: 20px; font-size: 14px; display: flex; gap: 8px; color: #64748b; }}
.nav-breadcrumbs a {{ color: #94a3b8; text-decoration: none; }}
.nav-breadcrumbs a:hover {{ color: #f8fafc; }}
.header {{ display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid #1e293b; padding-bottom: 20px; flex-wrap: wrap; gap: 12px; }}
h1 {{ margin: 0; font-size: 26px; display: flex; align-items: center; gap: 12px; }}
.domain-pill {{ font-size: 13px; font-weight: normal; padding: 4px 10px; border-radius: 999px; background: rgba(255,255,255,0.08); color: {p_cfg["badge_color"]}; border: 1px solid rgba(255,255,255,0.1); }}
.hero {{ background: linear-gradient(180deg, #131b2e 0%, #0d1527 100%); border: 1px solid #1e293b; border-radius: 18px; padding: 24px; margin: 24px 0; }}
.hero-title {{ font-size: 20px; font-weight: bold; margin-bottom: 8px; color: #f8fafc; }}
.hero-desc {{ color: #94a3b8; line-height: 1.6; font-size: 15px; }}
.grid {{ display: grid; grid-template-columns: repeat(3, minmax(0,1fr)); gap: 14px; margin: 20px 0; }}
.stat {{ background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.06); padding: 14px; border-radius: 12px; }}
.stat span {{ font-size: 12px; color: #64748b; display: block; }}
.stat b {{ font-size: 18px; margin-top: 4px; display: block; color: {p_cfg["badge_color"]}; }}
.section-title {{ font-size: 18px; font-weight: 600; margin: 32px 0 16px; color: #cbd5e1; }}
.card {{ background: #0f172a; border: 1px solid #1e293b; border-radius: 14px; padding: 18px; margin-bottom: 12px; }}
.row {{ display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; }}
.tag {{ font-size: 11px; padding: 3px 8px; border-radius: 6px; background: rgba(255,255,255,0.08); color: #94a3b8; text-transform: uppercase; }}
.badge {{ font-size: 12px; padding: 4px 10px; border-radius: 999px; background: rgba(56, 189, 248, 0.1); color: #38bdf8; margin-right: 6px; display: inline-block; margin-bottom: 6px; }}
ul.rules {{ margin: 8px 0 0; padding-left: 20px; color: #94a3b8; font-size: 14px; line-height: 1.7; }}
.muted {{ color: #64748b; font-size: 14px; }}
@media(max-width: 600px) {{
  .grid {{ grid-template-columns: 1fr; }}
  .row {{ flex-direction: column; }}
}}
</style>
</head>
<body>
{GLOBAL_NAV_HTML}
<main class="wrap">
  <div class="nav-breadcrumbs">
    <a href="/">首頁</a> <span>/</span>
    <a href="/personas/">AI 角色神殿</a> <span>/</span>
    <span style="color: #cbd5e1;">{p_cfg["name"]}</span>
  </div>

  <div class="header">
    <div>
      <h1><span>{p_cfg["domain_icon"]} {p_cfg["name"]}</span> <span class="domain-pill">{p_cfg["domain"]}</span></h1>
      <div class="muted" style="margin-top: 4px;">Agent ID: {p_cfg["agent_id"]}</div>
    </div>
    <div>
      <a href="{p_cfg["project_url"]}" style="text-decoration: none; color: #38bdf8; font-size: 13px; font-weight: 600; background: rgba(56,189,248,0.12); padding: 6px 14px; border-radius: 8px; border: 1px solid rgba(56,189,248,0.25);">
        🔗 前往關聯場館：{p_cfg["project_label"]} →
      </a>
    </div>
  </div>

  {special_banner}

  <section class="hero">
    <div class="hero-title">核心使命 (Mission)</div>
    <div class="hero-desc">{mission or activity.get("current", {}).get("title", "")}</div>
    <div class="grid">
      <div class="stat"><span>當前活動狀態</span><b>{activity.get("current", {}).get("focus_label", "自主運作")}</b></div>
      <div class="stat"><span>真實記錄事件</span><b>{activity.get("activity_count", 0)} 筆</b></div>
      <div class="stat"><span>神經網絡健康</span><b>{activity.get("health", {}).get("persona.core", "HEALTHY").upper()}</b></div>
    </div>
  </section>

  <div class="section-title">人格核心價值觀 (Core Invariants)</div>
  <div class="card">
    <div>{values_html or '<span class="muted">標準規範</span>'}</div>
    {f'<div style="margin-top:14px;font-size:13px;color:#cbd5e1;font-weight:600;">不可逾越之天規 (Forbidden Boundaries)：</div><ul class="rules">{forbidden_html}</ul>' if forbidden_html else ''}
  </div>

  <div class="section-title">真實生命軌跡與事件總帳 ({activity.get("activity_count", 0)} 筆紀錄)</div>
  <section class="timeline">
    {recent_html}
  </section>
</main>
</body>
</html>"""


def render_portal_hub(personas_info: list[dict[str, Any]]) -> str:
    cards_html = ""
    for p in personas_info:
        room_btn = f'<a href="/mio-room/" style="font-size:12px;color:#f472b6;margin-right:12px;text-decoration:none;">🌸 晴湖小築房間</a>' if p['slug'] == 'mio' else ''
        cards_html += f"""
        <div class="portal-card">
          <div class="card-header">
            <span class="icon">{p['domain_icon']}</span>
            <span class="badge" style="color:{p['badge_color']};border-color:{p['badge_color']}33;background:{p['badge_color']}11">{p['domain']}</span>
          </div>
          <div class="card-name">{p['name']}</div>
          <div class="card-desc">{p['mission']}</div>
          <div class="card-footer">
            <span class="events-count">📊 {p['events_count']} 筆真實事件</span>
            <div style="display:flex;align-items:center;">
              {room_btn}
              <a href="/personas/{p['slug']}/" class="arrow" style="text-decoration:none;">深入觀測窗 →</a>
            </div>
          </div>
        </div>
        """

    return f"""<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>AgentOS AI 角色殿堂 · 諸神列柱 (Universal Persona Portal)</title>
<style>
:root {{
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "PingFang TC", "Noto Sans TC", sans-serif;
  color: #f8fafc;
  background: #070b14;
}}
body {{ margin: 0; padding: 0; min-height: 100vh; }}
.wrap {{ max-width: 1180px; margin: auto; padding: 24px 24px 96px; }}

.hero {{ text-align: center; margin: 40px 0 50px; }}
.hero h1 {{ font-size: 38px; margin: 0 0 14px; font-weight: 800; background: linear-gradient(135deg, #ffffff 0%, #94a3b8 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }}
.hero p {{ font-size: 16px; color: #94a3b8; max-width: 720px; margin: 0 auto; line-height: 1.7; }}

.portal-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); gap: 24px; }}
.portal-card {{
  background: linear-gradient(180deg, #111827 0%, #0b1120 100%);
  border: 1px solid #1f2937;
  border-radius: 20px;
  padding: 24px;
  color: inherit;
  transition: all 0.25s ease;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
}}
.portal-card:hover {{
  transform: translateY(-4px);
  border-color: #38bdf8;
  box-shadow: 0 20px 40px rgba(0,0,0,0.5);
}}
.card-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }}
.icon {{ font-size: 32px; }}
.badge {{ font-size: 12px; padding: 4px 10px; border-radius: 999px; border: 1px solid; font-weight: 600; }}
.card-name {{ font-size: 20px; font-weight: 700; margin-bottom: 8px; color: #f1f5f9; }}
.card-desc {{ font-size: 14px; color: #94a3b8; line-height: 1.6; margin-bottom: 24px; flex-grow: 1; }}
.card-footer {{ display: flex; justify-content: space-between; align-items: center; border-top: 1px solid #1f2937; padding-top: 16px; font-size: 13px; }}
.events-count {{ color: #64748b; }}
.arrow {{ color: #38bdf8; font-weight: 600; }}
</style>
</head>
<body>
{GLOBAL_NAV_HTML}
<main class="wrap">
  <section class="hero">
    <h1>AI Agent 諸神列柱</h1>
    <p>全自主生命體系的人格核心 (Character Core)、心境歷程 (Persona State) 與事件總帳 (Event Ledger)。每個角色皆具備獨立 IR、生活空間與不可逾越之天規。</p>
  </section>

  <div class="portal-grid">
    {cards_html}
  </div>
</main>
</body>
</html>"""


def main():
    DIST_PERSONAS.mkdir(parents=True, exist_ok=True)
    PUBLIC_PERSONAS.mkdir(parents=True, exist_ok=True)
    summary_list = []

    for p_cfg in PERSONA_MAPPINGS:
        slug = p_cfg["slug"]
        for base in [DIST_PERSONAS, PUBLIC_PERSONAS]:
            target_dir = base / slug
            target_dir.mkdir(parents=True, exist_ok=True)

        activity = generate_activity_json(p_cfg)
        activity_str = json.dumps(activity, ensure_ascii=False, indent=2)
        (DIST_PERSONAS / slug / "activity.json").write_text(activity_str, encoding="utf-8")
        (PUBLIC_PERSONAS / slug / "activity.json").write_text(activity_str, encoding="utf-8")

        # Generate persona index.html for ALL personas (including mio!)
        page_html = render_persona_page(p_cfg, activity)
        (DIST_PERSONAS / slug / "index.html").write_text(page_html, encoding="utf-8")
        (PUBLIC_PERSONAS / slug / "index.html").write_text(page_html, encoding="utf-8")

        core = load_json(p_cfg["data_dir"] / "character_core.json")
        summary_list.append({
            "slug": slug,
            "name": p_cfg["name"],
            "domain": p_cfg["domain"],
            "domain_icon": p_cfg["domain_icon"],
            "badge_color": p_cfg["badge_color"],
            "mission": core.get("mission") or activity.get("current", {}).get("title", ""),
            "events_count": activity.get("activity_count", 0),
        })

    # Render Central Persona Portal Hub to both dist and public
    hub_html = render_portal_hub(summary_list)
    (DIST_PERSONAS / "index.html").write_text(hub_html, encoding="utf-8")
    (PUBLIC_PERSONAS / "index.html").write_text(hub_html, encoding="utf-8")
    print(f"✅ Successfully synchronized all 9 personas to {DIST_PERSONAS} and {PUBLIC_PERSONAS}")


if __name__ == "__main__":
    main()
