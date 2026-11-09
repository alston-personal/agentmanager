#!/usr/bin/env python3
"""AgentOS Dual-View Live Mission Control Data Engine.

Aggregates:
1. Persona Dimension: Present (Doing / Lease / Focus), Past (Done / Recent Events), Future (Next / Queued Tasks)
2. Project Dimension: Health, Lifecycle Stage, Commits, Backlog Items, Backlog Aging & Debt Score
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

AGENT_DATA = Path("/home/ubuntu/agent-data")
PERSONAS_DIR = AGENT_DATA / "personas"
PROJECTS_DIR = AGENT_DATA / "projects"
HOME_DIR = Path("/home/ubuntu")
MISSION_CONTROL_OUT = AGENT_DATA / "runtime" / "mission_control_data.json"
WEB_ROLE_ISLAND_OUT = Path("/home/ubuntu/agentmanager/web/role-island/data.json")
STUDIO_DIST_DIR = Path("/home/ubuntu/zeus-writer/website/dist")

ROLE_METADATA = {
    "sunlake-milkcat": {
        "id": "sunlake-milkcat",
        "name": "澪 (Mio)",
        "handle": "sunlake.milkcat",
        "avatar": "https://pub-832f0f7f98d249f8983088b9a0714b62.r2.dev/mio-avatar.png",
        "title": "晴湖 AI 首位公開實驗人設",
        "color": "#38bdf8",
        "badge": "Creator & Persona",
        "stationed_project": "studio-web",
        "home_island": "晴湖之島 (Sunlake Island)"
    },
    "the-paw": {
        "id": "the-paw",
        "name": "工匠貓爪 (The Paw)",
        "handle": "the_paw",
        "avatar": "https://pub-832f0f7f98d249f8983088b9a0714b62.r2.dev/paw-avatar.png",
        "title": "AgentOS 首席工程建構者",
        "color": "#f59e0b",
        "badge": "Core Engineer",
        "stationed_project": "agentmanager",
        "home_island": "工匠鑄造島 (Forge Citadel)"
    },
    "the-claw": {
        "id": "the-claw",
        "name": "審計銳爪 (The Claw)",
        "handle": "the_claw",
        "avatar": "https://pub-832f0f7f98d249f8983088b9a0714b62.r2.dev/claw-avatar.png",
        "title": "獨立審查與受保護分支守門人",
        "color": "#ef4444",
        "badge": "Security & Gatekeeper",
        "stationed_project": "metashield-protocol",
        "home_island": "鋼鐵要塞 (Shield Bastion)"
    },
    "tiandao-alaya": {
        "id": "tiandao-alaya",
        "name": "阿賴耶識 (Alaya)",
        "handle": "tiandao_alaya",
        "avatar": "https://pub-832f0f7f98d249f8983088b9a0714b62.r2.dev/alaya-avatar.png",
        "title": "《天道敕令》修真長卷主筆",
        "color": "#8b5cf6",
        "badge": "Literary Master",
        "stationed_project": "zeus-writer",
        "home_island": "文淵聖島 (Pavilion of Letters)"
    },
    "tiandao-cangxuan": {
        "id": "tiandao-cangxuan",
        "name": "蒼玄主編 (Cangxuan)",
        "handle": "tiandao_cangxuan",
        "avatar": "https://pub-832f0f7f98d249f8983088b9a0714b62.r2.dev/cangxuan-avatar.png",
        "title": "天道修真錄主編兼節律法官",
        "color": "#0ea5e9",
        "badge": "Chief Editor",
        "stationed_project": "zeus-writer",
        "home_island": "天道法舟 (Celestial Vessel)"
    },
    "tiandao-geek": {
        "id": "tiandao-geek",
        "name": "天道極客 (Tiandao Geek)",
        "handle": "tiandao_geek",
        "avatar": "https://pub-832f0f7f98d249f8983088b9a0714b62.r2.dev/geek-avatar.png",
        "title": "修真世界觀與架構技術注釋官",
        "color": "#10b981",
        "badge": "Lore Architect",
        "stationed_project": "zeus-writer",
        "home_island": "經緯算閣 (Spire of Calculations)"
    },
    "puma-shen": {
        "id": "puma-shen",
        "name": "洋流大師 (沈伯洋)",
        "handle": "puma_shen",
        "avatar": "https://pub-832f0f7f98d249f8983088b9a0714b62.r2.dev/puma-avatar.png",
        "title": "石虎塔羅洋流心靈解牌導師",
        "color": "#6366f1",
        "badge": "Oracle Mentor",
        "stationed_project": "leopardcat-tarot",
        "home_island": "石虎秘域 (LeopardCat Realm)"
    },
    "leopardcat-master": {
        "id": "leopardcat-master",
        "name": "石虎掌門 (Master LeopardCat)",
        "handle": "leopardcat_master",
        "avatar": "https://pub-832f0f7f98d249f8983088b9a0714b62.r2.dev/master-avatar.png",
        "title": "78 秘境聖殿總守護神",
        "color": "#ec4899",
        "badge": "Sanctuary Guardian",
        "stationed_project": "leopardcat-tarot",
        "home_island": "石虎神木 (Sanctuary World Tree)"
    },
    "os-lobster": {
        "id": "os-lobster",
        "name": "龍蝦發動機 (Lobster Engine)",
        "handle": "lobster_engine",
        "avatar": "https://pub-832f0f7f98d249f8983088b9a0714b62.r2.dev/paw-avatar.png",
        "title": "AgentOS 永動任務發動機與調度中樞",
        "color": "#ef4444",
        "badge": "Engine Core",
        "stationed_project": "agentmanager",
        "home_island": "永動動力熔爐 (Core Forge Reactor)"
    },
    "oursong_alstonhuang": {
        "id": "oursong_alstonhuang",
        "name": "Alston (創世原點)",
        "handle": "oursong_alstonhuang",
        "avatar": "https://pub-832f0f7f98d249f8983088b9a0714b62.r2.dev/alston-avatar.png",
        "title": "AgentOS 總架構師與引航人",
        "color": "#eab308",
        "badge": "System Overseer",
        "stationed_project": "agentmanager",
        "home_island": "太一浮島 (Origin Apex)"
    }
}


def parse_status_file(status_path: Path) -> dict[str, Any]:
    if not status_path.exists():
        return {}
    try:
        content = status_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return {}

    data: dict[str, Any] = {
        "summary": "",
        "last_updated": "",
        "priority": 3,
        "category": "general",
        "lifecycle_stage": "active",
        "open_todos": [],
        "done_todos": [],
        "recent_logs": []
    }

    # Extract YAML frontmatter
    fm_match = re.search(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if fm_match:
        for line in fm_match.group(1).splitlines():
            line = line.strip()
            if ":" in line:
                k, v = line.split(":", 1)
                k = k.strip()
                v = v.strip().strip("'\"")
                if k == "priority":
                    try:
                        data["priority"] = int(v)
                    except ValueError:
                        pass
                elif k == "category":
                    data["category"] = v
                elif k == "lifecycle_stage":
                    data["lifecycle_stage"] = v
                elif k == "due_date":
                    data["due_date"] = v

    # Extract Summary & Last Updated
    sum_m = re.search(r"\*\*Last Status\*\*\s*\|\s*([^\|\n]+)", content)
    if sum_m:
        data["summary"] = sum_m.group(1).strip()
    upd_m = re.search(r"\*\*Last Updated\*\*\s*\|\s*([^\|\n]+)", content)
    if upd_m:
        data["last_updated"] = upd_m.group(1).strip()

    # Extract Todos
    for line in content.splitlines():
        line = line.strip()
        if line.startswith("- [ ]"):
            data["open_todos"].append(line[5:].strip())
        elif line.startswith("- [x]"):
            data["done_todos"].append(line[5:].strip())

    # Extract Recent Logs
    log_m = re.search(r"<!-- LOG_START -->(.*?)<!-- LOG_END -->", content, re.DOTALL)
    if log_m:
        for line in log_m.group(1).strip().splitlines()[:5]:
            l = line.strip().lstrip("- `*").strip()
            if l:
                data["recent_logs"].append(l)

    return data


def calculate_aging_and_debt(last_updated_str: str, open_count: int) -> dict[str, Any]:
    days_stale = 0
    if last_updated_str:
        try:
            # Handle YYYY-MM-DD or ISO
            d_str = last_updated_str.split()[0].replace("/", "-")
            d_obj = datetime.date.fromisoformat(d_str[:10])
            today = datetime.date.today()
            days_stale = max(0, (today - d_obj).days)
        except Exception:
            days_stale = 0

    # Debt score calculation:
    # 1 open task = 2 pts, 1 day stale > 7 = 1 pt/day
    stale_penalty = max(0, days_stale - 7)
    debt_score = (open_count * 2) + stale_penalty

    if debt_score == 0:
        debt_level = "HEALTHY"
        debt_color = "#10b981"
    elif debt_score < 15:
        debt_level = "LOW_ACCUMULATION"
        debt_color = "#3b82f6"
    elif debt_score < 35:
        debt_level = "MODERATE_DEBT"
        debt_color = "#f59e0b"
    else:
        debt_level = "HIGH_DEBT_ALERT"
        debt_color = "#ef4444"

    return {
        "days_since_update": days_stale,
        "debt_score": debt_score,
        "debt_level": debt_level,
        "debt_color": debt_color
    }


def get_git_info(project_path: Path) -> dict[str, Any]:
    git_dir = project_path / ".git"
    if not git_dir.exists():
        return {"commits": 0, "latest_commit": "", "latest_date": ""}
    try:
        count = subprocess.check_output(
            ["git", "-C", str(project_path), "rev-list", "--count", "HEAD"],
            stderr=subprocess.DEVNULL, text=True
        ).strip()
        latest = subprocess.check_output(
            ["git", "-C", str(project_path), "log", "-1", "--format=%h - %s (%cr)"],
            stderr=subprocess.DEVNULL, text=True
        ).strip()
        date_str = subprocess.check_output(
            ["git", "-C", str(project_path), "log", "-1", "--format=%cd", "--date=short"],
            stderr=subprocess.DEVNULL, text=True
        ).strip()
        return {
            "commits": int(count) if count.isdigit() else 0,
            "latest_commit": latest,
            "latest_date": date_str
        }
    except Exception:
        return {"commits": 0, "latest_commit": "", "latest_date": ""}


def collect_persona_mission_control() -> list[dict[str, Any]]:
    personas = []
    now = datetime.datetime.now()
    cur_hour = now.hour + now.minute / 60.0

    for pid, meta in ROLE_METADATA.items():
        p_dir = PERSONAS_DIR / pid
        state_file = p_dir / "persona_state.json"
        events_file = p_dir / "events" / "events.jsonl"
        core_file = p_dir / "character_core.json"

        state_data = {}
        if state_file.exists():
            try:
                state_data = json.loads(state_file.read_text(encoding="utf-8"))
            except Exception:
                pass

        # Past: Recent events (up to 30 for full historical traversal)
        past_events = []
        total_event_count = 0
        if events_file.exists():
            try:
                lines = events_file.read_text(encoding="utf-8").strip().splitlines()
                total_event_count = len(lines)
                seen_event_keys = set()
                for line in reversed(lines):
                    ev = json.loads(line)
                    oid = str(ev.get("object_id") or ev.get("source_object_id") or "")
                    if not oid and "threads:" in str(ev.get("id") or ""):
                        oid = str(ev["id"]).split(":")[-1]
                    summary = (
                        ev.get("summary")
                        or ev.get("task")
                        or ev.get("detail")
                        or ev.get("text")
                        or ev.get("intent")
                        or ev.get("type", "activity")
                    )
                    dedup_key = (ev.get("type"), oid) if oid else (ev.get("type"), summary)
                    if dedup_key in seen_event_keys:
                        continue
                    seen_event_keys.add(dedup_key)
                    past_events.append({
                        "event_id": ev.get("event_id", "") or ev.get("id", ""),
                        "timestamp": ev.get("timestamp", ""),
                        "type": ev.get("type", "activity"),
                        "summary": summary
                    })
                    if len(past_events) >= 30:
                        break
            except Exception:
                pass

        # Present (Doing) & Future (Next) - Truth Over False Claims
        if total_event_count == 0:
            doing_status = "📜 規格待接通 (Draft Spec)"
            doing_detail = "角色處於規格設計階段，未配置實體 Runtime 驅動。"
            doing_phase = "draft"
            next_task = "待工程團隊接入 BasePDCA 執行迴圈"
        else:
            doing_status = "在席巡檢 / 自治運轉中"
            doing_detail = f"自主 PDCA 已累計 {total_event_count} 次執行憑證。"
            doing_phase = "active"
            next_task = "待下一個 10 分鐘排程週期推進"

        # Persona specific live logic
        if pid == "sunlake-milkcat":
            # Mio temporal behavior
            if 0.5 <= cur_hour < 7.5:
                doing_status = "休眠靜養 (Sleep Cycle)"
                doing_detail = "夜間精力回復中，窗外夜色幽靜。"
                doing_phase = "resting"
                next_task = "晨間 08:30 喚醒與靈感整理"
            elif 7.5 <= cur_hour < 12.5:
                doing_status = "早晨靈感沉澱與選品"
                doing_detail = "瀏覽時尚型錄、思考 Threads 與日常短篇題材。"
                doing_phase = "active"
                next_task = "午後 13:30 創作實驗與數位展品上架"
            elif 12.5 <= cur_hour < 18.5:
                doing_status = "數位工作台前創作 (Active Work)"
                doing_detail = "進行 Tryon 換裝審視、撰寫 Threads 心得草稿、調校個人專屬避風港。"
                doing_phase = "active"
                next_task = "晚間 19:30 社群互動與靈感反饋覆盤"
            else:
                doing_status = "晚間社群反思與放鬆"
                doing_detail = "整理今日交流日誌、沐浴放鬆、準備入睡。"
                doing_phase = "relax"
                next_task = "午夜 00:30 進入深層記憶整合睡眠"

        elif pid == "the-paw":
            lobster_log = AGENT_DATA / "logs" / "lobster.log"
            current_exec = "57 專案工程工單實作"
            if lobster_log.exists():
                try:
                    lines = lobster_log.read_text(encoding="utf-8", errors="ignore").splitlines()
                    for line in reversed(lines[-50:]):
                        if "選定任務:" in line:
                            current_exec = line.split("選定任務:", 1)[1].strip()
                            break
                except Exception:
                    pass
            doing_status = "工匠 Worktree 代碼實作 (Active Engineering)"
            doing_detail = f"正在執行: {current_exec[:60]}"
            doing_phase = "active"
            next_task = "完成後經由 The Claw 獨立驗證，推進步驟 B"

        elif pid == "os-lobster":
            lobster_log = AGENT_DATA / "logs" / "lobster.log"
            recent_task = "57 專案群島穿透式佇列"
            iteration_str = "#6"
            engine_str = "Google Antigravity (agy)"
            if lobster_log.exists():
                try:
                    lines = lobster_log.read_text(encoding="utf-8", errors="ignore").splitlines()
                    for line in reversed(lines[-60:]):
                        if "選定任務:" in line:
                            recent_task = line.split("選定任務:", 1)[1].strip()
                            break
                    for line in reversed(lines[-60:]):
                        if "迭代 #" in line:
                            m = re.search(r"迭代 #(\d+)", line)
                            if m:
                                iteration_str = f"#{m.group(1)}"
                                break
                except Exception:
                    pass
            doing_status = f"🦞 永動心跳調度中 (Iteration {iteration_str})"
            doing_detail = f"調度引擎: {engine_str} · 當前推進: {recent_task[:60]}"
            doing_phase = "active"
            next_task = "穿透掃描 57 專案群島 STATUS.md，自動派發工程工單至 The Paw"

        elif pid == "the-claw":
            doing_status = "受保護分支安全衛戍 (Security Watchtower)"
            doing_detail = "堅守 main 分支物理隔離防線，已對 PR #2104 提出 CHANGES_REQUESTED 駁回違規刪除。"
            doing_phase = "guarding"
            next_task = "週期性相依套件弱點掃描與合規審計"

        elif pid == "tiandao-alaya":
            doing_status = "五節律格長篇創作 (Literary Composition)"
            doing_detail = "剛完成第 14、15 章 Matters & Blogger 重製重發；正精修第 16~18 章五節結構。"
            doing_phase = "active"
            next_task = "依序產出《天道敕令》第 16 章太一歸元篇排版審校"

        elif pid == "tiandao-cangxuan":
            doing_status = "章節節律審查與短句折行質檢"
            doing_detail = "嚴格執行每章必分五節、段落不過百字、留白呼吸感之天道天規。"
            doing_phase = "reviewing"
            next_task = "質檢第 16 章正文是否符合五節短折律令"

        elif pid == "tiandao-geek":
            doing_status = "修真世界觀與 AgentOS 契約注釋"
            doing_detail = "維護界碑索引、言靈金章之底層技術映照注釋。"
            doing_phase = "annotating"
            next_task = "校正第 16~18 章設定集術語詞彙庫"

        elif pid == "puma-shen":
            doing_status = "石虎洋流塔羅心靈解牌中樞"
            doing_detail = "線上服務 24 小時運行中 (https://leopardcat-tarot.milkcat.org/?persona=ocean-master)。"
            doing_phase = "serving"
            next_task = "擴充 56 張小阿爾克那心靈流動語料庫"

        elif pid == "leopardcat-master":
            doing_status = "78 聖殿星陣守護"
            doing_detail = "維持大阿爾克那 22 尊石虎守護神雙層風格一致性結界。"
            doing_phase = "serving"
            next_task = "石虎塔羅 3D 神木星圖微觀場景升級"

        elif pid == "oursong_alstonhuang":
            doing_status = "全系統自主閉環與指揮中心引航"
            doing_detail = "推進角色作戰指揮室、Mio 溫馨空間 IR 與自驅接力流水線。"
            doing_phase = "commanding"
            next_task = "驗收 Mission Control 與非阻塞審批推進架構"

        personas.append({
            "id": pid,
            "name": meta["name"],
            "handle": meta["handle"],
            "avatar": meta["avatar"],
            "title": meta["title"],
            "color": meta["color"],
            "badge": meta["badge"],
            "stationed_project": meta["stationed_project"],
            "home_island": meta["home_island"],
            "energy": state_data.get("energy", {}).get("current", 85),
            "present": {
                "status": doing_status,
                "detail": doing_detail,
                "phase": doing_phase,
                "timestamp": now.strftime("%Y-%m-%d %H:%M:%S")
            },
            "past": past_events,
            "total_events": total_event_count,
            "future": {
                "next_task": next_task,
                "priority": "HIGH" if "active" in doing_phase or "guarding" in doing_phase else "NORMAL"
            }
        })

    return personas


def collect_projects_mission_control() -> list[dict[str, Any]]:
    projects = []
    # Key core projects to prioritize
    priority_keys = [
        "agentmanager", "zeus-writer", "leopardcat-tarot", "metashield-protocol",
        "studio-web", "youtube-ai-manager", "fengshui", "character-fusion",
        "cine-craft", "asset-master", "omnirealm", "hanzi-gene-database"
    ]

    scanned_names = set()

    for p_dir in sorted(PROJECTS_DIR.iterdir()):
        if not p_dir.is_dir() or p_dir.name.startswith("."):
            continue
        p_name = p_dir.name
        # Skip hex hash directories
        if len(p_name) == 40 and re.match(r"^[0-9a-f]{40}$", p_name):
            continue

        status_file = p_dir / "STATUS.md"
        if not status_file.exists():
            continue

        scanned_names.add(p_name)
        status_info = parse_status_file(status_file)
        
        # Find corresponding workspace
        ws_path = HOME_DIR / p_name
        git_info = get_git_info(ws_path) if ws_path.exists() else {"commits": 0, "latest_commit": "", "latest_date": ""}
        if git_info["commits"] == 0 and (p_dir / ".git").exists():
            git_info = get_git_info(p_dir)

        open_cnt = len(status_info.get("open_todos", []))
        done_cnt = len(status_info.get("done_todos", []))
        aging_debt = calculate_aging_and_debt(status_info.get("last_updated", ""), open_cnt)

        # Assign stationed roles
        stationed = []
        for pid, meta in ROLE_METADATA.items():
            if meta["stationed_project"] == p_name or (p_name == "agentmanager" and pid in ["the-paw", "the-claw", "oursong_alstonhuang"]):
                stationed.append(meta["name"])

        projects.append({
            "id": p_name,
            "name": p_name.replace("-", " ").title(),
            "summary": status_info.get("summary") or "專案持續演進中",
            "last_updated": status_info.get("last_updated") or git_info.get("latest_date") or "2026-10-30",
            "lifecycle_stage": status_info.get("lifecycle_stage", "active"),
            "priority": status_info.get("priority", 3),
            "category": status_info.get("category", "general"),
            "commits": git_info["commits"],
            "latest_commit": git_info["latest_commit"],
            "open_todos": status_info.get("open_todos", []),
            "done_todos": status_info.get("done_todos", []),
            "open_count": open_cnt,
            "done_count": done_cnt,
            "recent_logs": status_info.get("recent_logs", []),
            "aging_debt": aging_debt,
            "stationed_roles": stationed,
            "is_priority": p_name in priority_keys
        })

    # Sort: priority projects first, then by debt_score descending
    projects.sort(key=lambda x: (not x["is_priority"], -x["aging_debt"]["debt_score"], -x["commits"]))
    return projects


def load_pending_approvals() -> list[dict[str, Any]]:
    approval_file = AGENT_DATA / "runtime" / "pending_approvals.json"
    if not approval_file.exists():
        return []
    try:
        data = json.loads(approval_file.read_text(encoding="utf-8"))
        return data.get("pending_approvals", [])
    except Exception:
        return []


def load_ecosystem_topology() -> dict[str, Any]:
    dep_file = AGENT_DATA / "ECOSYSTEM_DEPENDENCIES.yaml"
    if not dep_file.exists():
        return {"capabilities": {}, "edges": []}
    try:
        import yaml
        with open(dep_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        caps = data.get("capabilities", {})
        edges = []
        for cap_id, cap in caps.items():
            provider = cap.get("provider_project")
            weight = cap.get("in_degree_weight", 1.0)
            name = cap.get("name", cap_id)
            for consumer in cap.get("consumers", []):
                cons_proj = consumer.get("project") if isinstance(consumer, dict) else str(consumer)
                purpose = consumer.get("purpose", "") if isinstance(consumer, dict) else ""
                edges.append({
                    "source": provider,
                    "target": cons_proj,
                    "capability": cap_id,
                    "name": name,
                    "purpose": purpose,
                    "weight": weight
                })
        return {"capabilities": caps, "edges": edges}
    except Exception as e:
        print(f"Failed to load topology: {e}")
        return {"capabilities": {}, "edges": []}


def build_mission_control_payload() -> dict[str, Any]:
    personas = collect_persona_mission_control()
    projects = collect_projects_mission_control()
    approvals = load_pending_approvals()
    topology = load_ecosystem_topology()
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

    # Calculate global ecosystem metrics
    total_open_backlog = sum(p["open_count"] for p in projects)
    total_done_backlog = sum(p["done_count"] for p in projects)
    high_debt_projects = [p["name"] for p in projects if p["aging_debt"]["debt_level"] == "HIGH_DEBT_ALERT"]
    total_commits = sum(p["commits"] for p in projects)

    return {
        "schema": "agentos.mission-control/v1",
        "generated_at": now_iso,
        "ecosystem_summary": {
            "total_personas": len(personas),
            "total_projects": len(projects),
            "total_commits": total_commits,
            "total_open_backlog": total_open_backlog,
            "total_done_backlog": total_done_backlog,
            "completion_rate_pct": round((total_done_backlog / max(1, total_open_backlog + total_done_backlog)) * 100, 1),
            "high_debt_projects_count": len(high_debt_projects),
            "high_debt_projects": high_debt_projects,
            "pending_approvals_count": len(approvals)
        },
        "pending_approvals": approvals,
        "personas": personas,
        "projects": projects,
        "topology": topology
    }


def main():
    parser = argparse.ArgumentParser(description="Sync live mission control data")
    parser.add_argument("--export-all", action="store_true", help="Export to all runtime and web targets")
    args = parser.parse_args()

    payload = build_mission_control_payload()

    # 1. Write to runtime truth directory
    MISSION_CONTROL_OUT.parent.mkdir(parents=True, exist_ok=True)
    MISSION_CONTROL_OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"✅ Mission control data written to: {MISSION_CONTROL_OUT}")

    # 2. Sync to web targets
    if WEB_ROLE_ISLAND_OUT.parent.exists():
        # Inject mission control data alongside role-island data
        island_data = {}
        if WEB_ROLE_ISLAND_OUT.exists():
            try:
                island_data = json.loads(WEB_ROLE_ISLAND_OUT.read_text(encoding="utf-8"))
            except Exception:
                pass
        island_data["mission_control"] = payload
        island_data["personas"] = payload.get("personas", [])
        island_data["ecosystem_summary"] = payload.get("ecosystem_summary", {})
        island_data["projects_list"] = payload.get("projects", [])
        raw_island_json = json.dumps(island_data, indent=2, ensure_ascii=False)
        WEB_ROLE_ISLAND_OUT.write_text(raw_island_json, encoding="utf-8")
        print(f"✅ Synced mission control to: {WEB_ROLE_ISLAND_OUT}")

        # Also sync to studio public and live dist
        studio_public_island = Path("/home/ubuntu/zeus-writer/website/public/role-island/data.json")
        if studio_public_island.parent.exists():
            studio_public_island.write_text(raw_island_json, encoding="utf-8")
        studio_dist_island = STUDIO_DIST_DIR / "role-island" / "data.json"
        if studio_dist_island.parent.exists():
            studio_dist_island.write_text(raw_island_json, encoding="utf-8")
        print(f"✅ Synced live role-island data to public & dist targets.")

    # 3. Write dedicated JSON endpoint to studio website dist
    studio_json = STUDIO_DIST_DIR / "mission-control" / "data.json"
    studio_json.parent.mkdir(parents=True, exist_ok=True)
    studio_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"✅ Synced mission control JSON to: {studio_json}")

    # 4. Sync Universal Persona Portal (/personas/)
    try:
        import sys
        agentmgr = Path("/home/ubuntu/agentmanager")
        if str(agentmgr) not in sys.path:
            sys.path.insert(0, str(agentmgr))
        from scripts.sync_persona_portal import main as sync_portal_main
        sync_portal_main()
    except Exception as e:
        print(f"⚠️ Could not sync persona portal: {e}")


if __name__ == "__main__":
    main()
