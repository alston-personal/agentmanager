#!/usr/bin/env python3
"""AgentOS Multi-Role Live Status & Execution Dashboard.

Displays the current state, active lease, runner adapter, latest verifiable
evidence/receipts, upcoming task queues, and project-based archipelago data.
"""
from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path
from typing import Any

RUNTIME_ROOT = Path("/home/ubuntu/agent-data/employee-runtime")
GOVERNANCE_FILE = Path("/home/ubuntu/agentmanager/governance/employee-worker-adapters-v2.json")
WEB_DATA_PATH = Path("/home/ubuntu/agentmanager/web/role-island/data.json")

ALL_PROJECTS = {
    "agentos-core": {
        "id": "agentos-core",
        "name": "AgentOS Core (核心基盤與調度中心)",
        "icon": "🏰",
        "level": 4,
        "level_title": "Lv 4 超級都會 (Metropolis)",
        "commits": 4755,
        "tagline": "調度核心、Worker Host、Git 鑄造廠與出港碼頭",
        "color": "#f59e0b",
        "repo": "alston-personal/agentmanager",
        "url": "https://github.com/alston-personal/agentmanager",
        "coords": {"x": 0, "y": 0, "z": 0},
        "description": "AgentOS 自治運行時與監督器中樞，處理代碼生命週期、租約分發、PR 交付與跨專案總調度。",
        "stationed_roles": ["the-paw", "agentos-spec-steward"],
        "backlog": [
            {"id": "core-1", "title": "驗證 PR #2104 之 GitHub Actions CI 狀態", "status": "pending_ci"},
            {"id": "core-2", "title": "推進 Issue #470 靜態驗證後續驗收議題", "status": "queued"},
            {"id": "core-3", "title": "自主 Worktree 代碼重構與單元測試覆蓋率增補", "status": "planned"}
        ]
    },
    "leopardcat-tarot": {
        "id": "leopardcat-tarot",
        "name": "LeopardCat Tarot (石虎塔羅星域)",
        "icon": "🔮",
        "level": 3,
        "level_title": "Lv 3 秘法城鎮 (Mystic Realm)",
        "commits": 270,
        "tagline": "78 張原創石虎大/小阿爾克那，洋流大師（沈伯洋 Persona）已正式上線解牌",
        "color": "#a855f7",
        "repo": "alston-personal/leopardcat-tarot",
        "url": "https://leopardcat-tarot.milkcat.org/?persona=ocean-master",
        "coords": {"x": -36, "y": 0, "z": -18},
        "description": "台灣石虎文化與西方神秘學融合之視覺創作引擎，具備雙層一致性美術與即時解讀功能，洋流大師專屬解牌體系已上線。",
        "stationed_roles": [],
        "backlog": [
            {"id": "tarot-1", "title": "【已上線】洋流大師・伯洋解牌上線 (https://leopardcat-tarot.milkcat.org/?persona=ocean-master)", "status": "done"},
            {"id": "tarot-2", "title": "小阿爾克那 56 張牌義語料庫微調", "status": "queued"}
        ]
    },
    "metashield": {
        "id": "metashield",
        "name": "MetaShield & Security (安全守護堡壘)",
        "icon": "🛡️",
        "level": 3,
        "level_title": "Lv 3 鋼鐵要塞 (Fortress Citadel)",
        "commits": 160,
        "tagline": "代碼靜態稽核、受保護分支防線、安全合規守門人",
        "color": "#ef4444",
        "repo": "alston-personal/metashield-protocol",
        "url": "https://github.com/alston-personal/agentmanager",
        "coords": {"x": 0, "y": 0, "z": -42},
        "description": "獨立審查堡壘與安全圍欄，負責獨立代碼檢驗 (The Claw)、受保護分支防護與防禦審計。",
        "stationed_roles": ["the-claw"],
        "backlog": [
            {"id": "sec-1", "title": "對 Paw PR #2104 進行獨立程式碼審查 (Review)", "status": "ready"},
            {"id": "sec-2", "title": "驗證受保護分支物理隔離邊界防線", "status": "queued"}
        ]
    },
    "zeus-writer": {
        "id": "zeus-writer",
        "name": "Zeus Writer (長文創作之殿)",
        "icon": "🏛️",
        "level": 2,
        "level_title": "Lv 2 書香聚落 (Cultural Town)",
        "commits": 50,
        "tagline": "百萬字長篇小說自動化起草、大綱審定與正文編撰",
        "color": "#3b82f6",
        "repo": "alston-personal/zeus-writer",
        "url": "https://studio.milkcat.org/novels/",
        "coords": {"x": 36, "y": 0, "z": -18},
        "description": "AI 自主小說創作系統，包含靈感之泉、手稿檔案庫、篇章審閱與靜態網站自動化部署。",
        "stationed_roles": ["zeus-writer"],
        "backlog": [
            {"id": "zeus-1", "title": "生成《正文/Ch06》章節大綱與角色對話設定", "status": "queued"},
            {"id": "zeus-2", "title": "執行 Chapter 06 萬字內文創作與語法一致性校正", "status": "planned"}
        ]
    },
    "fengshui": {
        "id": "fengshui",
        "name": "FengShui (地理風水排盤)",
        "icon": "🧭",
        "level": 2,
        "level_title": "Lv 2 八卦小島 (FengShui Town)",
        "commits": 34,
        "tagline": "玄空九星、八宅風水、空間格局動態圖層與即時吉凶研判",
        "color": "#06b6d4",
        "repo": "alston-personal/fengshui",
        "url": "https://studio.milkcat.org/fengshui/",
        "coords": {"x": 42, "y": 0, "z": 14},
        "description": "結合東方風水哲學與向量地圖排盤計算之專業分析引擎。",
        "stationed_roles": [],
        "backlog": [
            {"id": "fs-1", "title": "平面圖格局疊加層校準演算法增強", "status": "queued"}
        ]
    },
    "studio-web": {
        "id": "studio-web",
        "name": "Studio Web (官網展館門戶)",
        "icon": "🌐",
        "level": 1,
        "level_title": "Lv 1 公共港口 (Harbor Port)",
        "commits": 18,
        "tagline": "官方 3D 展館、訪客入口、展示公共傳送門",
        "color": "#10b981",
        "repo": "alston-personal/studio-web",
        "url": "https://studio.milkcat.org/",
        "coords": {"x": 20, "y": 0, "z": 36},
        "description": "Alston 個人宇宙與 AgentOS 之對外門戶，提供沈浸式 3D 展館與各專案即時預覽體驗。",
        "stationed_roles": [],
        "backlog": [
            {"id": "web-1", "title": "官方 3D 展館空間漫遊鏡頭路徑調整", "status": "queued"}
        ]
    },
    "support-me-block": {
        "id": "support-me-block",
        "name": "Support Me Block (贊助系統)",
        "icon": "☕",
        "level": 1,
        "level_title": "Lv 1 補給前哨 (Supply Outpost)",
        "commits": 22,
        "tagline": "開源贊助、區塊鏈與多渠道打賞模組",
        "color": "#f97316",
        "repo": "alston-personal/support-me-block",
        "url": "https://studio.milkcat.org/",
        "coords": {"x": 34, "y": 0, "z": 36},
        "description": "跨專案贊助與資金池管理組件，支援各微觀場館打賞回饋。",
        "stationed_roles": [],
        "backlog": [
            {"id": "sup-1", "title": "支付回調 Webhook 簽名驗證重構", "status": "planned"}
        ]
    },
    "youtube-ai-manager": {
        "id": "youtube-ai-manager",
        "name": "YouTube AI (影音營運島)",
        "icon": "📺",
        "level": 1,
        "level_title": "Lv 1 通訊雷達站 (Radar Outpost)",
        "commits": 4,
        "tagline": "影音頻道自動化掃描、SEO 標籤優化與成效分析",
        "color": "#ec4899",
        "repo": "alston-personal/youtube-ai-manager",
        "url": "https://studio.milkcat.org/",
        "coords": {"x": -20, "y": 0, "z": 36},
        "description": "影音營運與智慧雷達塔，負責頻道監控、標題縮圖 A/B 測試建議。",
        "stationed_roles": ["youtube-ai-manager"],
        "backlog": [
            {"id": "yt-1", "title": "頻道 API 授權白名單解鎖配置", "status": "blocked"},
            {"id": "yt-2", "title": "最新 5 支影片標題與描述 SEO 評估", "status": "planned"}
        ]
    },
    "if-tv-station": {
        "id": "if-tv-station",
        "name": "IF TV Station (IF 電視台)",
        "icon": "📻",
        "level": 1,
        "level_title": "Lv 1 廣播營地 (Broadcast Camp)",
        "commits": 6,
        "tagline": "虛擬影音節目生成與自動化串流轉播站",
        "color": "#eab308",
        "repo": "alston-personal/if-tv-station",
        "url": "https://studio.milkcat.org/iftv",
        "coords": {"x": -38, "y": 0, "z": 16},
        "description": "生成式 AI 電視節目架構，負責節目腳本轉影片渲染流程。",
        "stationed_roles": [],
        "backlog": [
            {"id": "iftv-1", "title": "節目資產上傳管道自動化測試", "status": "planned"}
        ]
    },
    "history-synthesizer": {
        "id": "history-synthesizer",
        "name": "History Synthesizer (歷史合成器)",
        "icon": "📜",
        "level": 1,
        "level_title": "Lv 1 考察營地 (Expedition Camp)",
        "commits": 6,
        "tagline": "多源史料合成、時空交叉考證與歷史脈絡圖譜",
        "color": "#84cc16",
        "repo": "alston-personal/history-synthesizer",
        "url": "https://studio.milkcat.org/",
        "coords": {"x": -42, "y": 0, "z": -2},
        "description": "將歷史文獻轉換為多維時空脈絡的自主推演工具。",
        "stationed_roles": [],
        "backlog": [
            {"id": "hist-1", "title": "時序爬蟲事件抽取管道建構", "status": "planned"}
        ]
    },
    "asset-master": {
        "id": "asset-master",
        "name": "Asset Master (數位資產管家)",
        "icon": "📦",
        "level": 0,
        "level_title": "Lv 0 拓荒小岩礁 (Barren Outpost)",
        "commits": 4,
        "tagline": "跨專案多媒體模型與紋理資產索引中樞",
        "color": "#64748b",
        "repo": "alston-personal/asset-master",
        "url": "https://studio.milkcat.org/",
        "coords": {"x": -34, "y": 0, "z": 36},
        "description": "3D 模型、音訊與貼圖之全域快取管理中樞。",
        "stationed_roles": [],
        "backlog": [
            {"id": "ast-1", "title": "全系統靜態資產目錄清查", "status": "planned"}
        ]
    },
    "hanzi-gene-database": {
        "id": "hanzi-gene-database",
        "name": "Hanzi Gene (漢字基因庫)",
        "icon": "🏝️",
        "level": 0,
        "level_title": "Lv 0 荒島岩礁 (Wild Reef)",
        "commits": 2,
        "tagline": "漢字部首演變、象形拓撲與文化基因語義樹",
        "color": "#94a3b8",
        "repo": "alston-personal/hanzi-gene-database",
        "url": "https://studio.milkcat.org/",
        "coords": {"x": -18, "y": 0, "z": -46},
        "description": "剛打下地基的草創荒島，只有一頂探險帳篷與測量旗幟，等待 AI 拓荒者開墾。",
        "stationed_roles": [],
        "backlog": [
            {"id": "hz-1", "title": "漢字象形拓撲構詞樹初始化", "status": "planned"}
        ]
    },
    "prophecy-verifier": {
        "id": "prophecy-verifier",
        "name": "Prophecy Verifier (預言驗證器)",
        "icon": "🗿",
        "level": 0,
        "level_title": "Lv 0 原始荒石島 (Untamed Wilds)",
        "commits": 0,
        "tagline": "時間序列命題、歷史預言回溯與準確度統計檢定",
        "color": "#475569",
        "repo": "alston-personal/prophecy-verifier",
        "url": "https://studio.milkcat.org/prophecy/",
        "coords": {"x": 18, "y": 0, "z": -46},
        "description": "全新立項之原始荒島，立有一根古老測量木樁，等待第一批代碼交付開拓！",
        "stationed_roles": [],
        "backlog": [
            {"id": "pv-1", "title": "專案代碼倉庫初次 Bootstrap 與 CI 設置", "status": "planned"}
        ]
    },
    "cine-craft": {
        "id": "cine-craft",
        "name": "CineCraft (影眸剪映工坊)",
        "icon": "🎞️",
        "level": 2,
        "level_title": "Lv 2 剪映工坊 (Editing Atelier)",
        "commits": 12,
        "tagline": "AI 影音高光切片、9:16 Shorts 自動剪輯與合輯生成流水線",
        "color": "#f43f5e",
        "repo": "alston-personal/youtube-ai-manager",
        "url": "https://studio.milkcat.org/",
        "coords": {"x": -26, "y": 0, "z": 44},
        "description": "負責自龐大影音素材庫自動識別精華時間戳，透過 ffmpeg 自動剪裁直式短影片與高光合輯。",
        "stationed_roles": ["the-lens"],
        "backlog": [
            {"id": "cine-1", "title": "自動批量 Shorts 影片渲染排程管道 (shorts_maker.py)", "status": "queued"},
            {"id": "cine-2", "title": "多平台發布適配器 (Shorts, Reels, TikTok)", "status": "planned"}
        ]
    },
    "character-fusion": {
        "id": "character-fusion",
        "name": "Character Fusion (小水滴視覺融合)",
        "icon": "💧",
        "level": 3,
        "level_title": "Lv 3 水晶工坊 (Crystal Forge)",
        "commits": 18,
        "tagline": "小水滴吉祥物與使用者肖像特徵 IR 權重融合引擎",
        "color": "#06b6d4",
        "repo": "alston-personal/agentmanager",
        "url": "https://studio.milkcat.org/character-fusion/",
        "coords": {"x": 28, "y": 0, "z": -28},
        "description": "運用 Character Blueprint 與 mode2IR 權重融合，產出高保真可愛小水滴吉祥物肖像。",
        "stationed_roles": ["zeus-writer"],
        "backlog": [
            {"id": "drop-1", "title": "【已驗收】Runner Window 煙霧測試產出真實 1.06MB Qwen PNG", "status": "done"},
            {"id": "drop-2", "title": "小水滴線上上傳互動 Web UI 前端介面", "status": "planned"}
        ]
    }
}

ROLE_QUEUES: dict[str, list[dict[str, str]]] = {
    "the-lens": [
        {"seq": 1, "task": "掃描 video_library.json 154 部已索引高能時間戳", "status": "active_scan", "target": "video_library.json"},
        {"seq": 2, "task": "依據幽默度切片自動渲染 9:16 Shorts (shorts_maker.py)", "status": "queued", "target": "CineCraft Pipeline"},
        {"seq": 3, "task": "YouTube OAuth Refresh Token 重新授權驗證", "status": "blocked", "target": "Google Cloud OAuth"}
    ],
    "the-paw": [
        {"seq": 1, "task": "驗證 PR #2104 之 GitHub CI 狀態與審查回饋", "status": "pending_ci", "target": "Core PR #2104"},
        {"seq": 2, "task": "Core #470 靜態驗證通過後，推進下一順位驗收議題", "status": "queued", "target": "Core Backlog"},
        {"seq": 3, "task": "自主 Worktree 代碼重構與單元測試覆蓋率增補", "status": "planned", "target": "Core Quality"}
    ],
    "the-claw": [
        {"seq": 1, "task": "針對 Paw PR #2104 進行獨立程式碼審查 (Independent Code Review)", "status": "ready", "target": "PR #2104 Review"},
        {"seq": 2, "task": "驗證受保護分支物理邊界 (Protected Branch Physical Fence)", "status": "queued", "target": "Governance Fence"},
        {"seq": 3, "task": "週期性安全相依套件與 CWE 弱點掃描", "status": "planned", "target": "Security Audit"}
    ],
    "zeus-writer": [
        {"seq": 1, "task": "生成《正文/Ch06》章節大綱與角色對話設定", "status": "queued", "target": "Ch06 Draft Outline"},
        {"seq": 2, "task": "執行 Chapter 06 萬字內文創作與語法一致性校正", "status": "planned", "target": "Ch06 Manuscript"},
        {"seq": 3, "task": "同步發布至 novels 靜態閱讀網站並產出 RSS", "status": "planned", "target": "Novel Web Deploy"}
    ],
    "agentos-spec-steward": [
        {"seq": 1, "task": "Core #197 O3 驗收閉環差距 (Closure Gap) 審計與簽核", "status": "active_eval", "target": "Issue #197 O3"},
        {"seq": 2, "task": "權限與能力契約 (Capability vs Authority) 一致性審查", "status": "queued", "target": "Governance Contract"},
        {"seq": 3, "task": "檢查各專案 STATUS.md 軟連結架構合規性", "status": "planned", "target": "Architecture Guard"}
    ],
    "youtube-ai-manager": [
        {"seq": 1, "task": "等待頻道 API 授權白名單以恢復唯讀掃描", "status": "blocked", "target": "Channel Allowlist"},
        {"seq": 2, "task": "執行最新 5 支影片標題與描述 SEO 評估", "status": "blocked", "target": "Video SEO Scan"},
        {"seq": 3, "task": "產出下週發布排程建議報告", "status": "planned", "target": "Content Calendar"}
    ]
}


def get_all_receipt_events() -> list[dict[str, Any]]:
    receipts_dir = RUNTIME_ROOT / "lifecycle/receipts"
    events = []
    if receipts_dir.exists():
        for r_file in receipts_dir.glob("*/*.json"):
            try:
                data = json.loads(r_file.read_text(encoding="utf-8"))
                aid = data.get("assignment_id", r_file.parent.name)
                gen = data.get("generation", 0)
                outcome = data.get("outcome", "unknown")
                rec_at = data.get("recorded_at", "")
                summary = data.get("result_summary") or {}

                # Determine role & project mapping
                role_id = "system"
                project_id = "agentos-core"
                if "paw" in aid:
                    role_id = "the-paw"
                    project_id = "agentos-core"
                elif "zeus" in aid:
                    role_id = "zeus-writer"
                    project_id = "zeus-writer"
                elif "claw" in aid:
                    role_id = "the-claw"
                    project_id = "metashield"
                elif "spec-steward" in aid:
                    role_id = "agentos-spec-steward"
                    project_id = "agentos-core"
                elif "youtube" in aid:
                    role_id = "youtube-ai-manager"
                    project_id = "youtube-ai-manager"

                events.append({
                    "id": f"{aid}-{gen}",
                    "assignment_id": aid,
                    "generation": gen,
                    "outcome": outcome,
                    "recorded_at": rec_at,
                    "role_id": role_id,
                    "project_id": project_id,
                    "stage": summary.get("bounded_stage", "runtime-execution"),
                    "summary": summary,
                    "commit_sha": summary.get("commit_sha", ""),
                    "bundle_path": summary.get("bundle_path", ""),
                    "blocker_code": summary.get("blocker_code", ""),
                    "raw_receipt": data
                })
            except Exception:
                continue

    # Add event for The Claw review on PR #2104
    events.append({
        "id": "the-claw-audit-899528e9",
        "assignment_id": "the-claw-offline-audit-v1",
        "generation": 2,
        "outcome": "rejected",
        "recorded_at": "2026-11-02T03:03:26Z",
        "role_id": "the-claw",
        "project_id": "metashield",
        "stage": "independent-review",
        "summary": {
            "target_commit": "899528e9276b2893d3a0c2ea8390e963d736bae7",
            "static_check": "FAIL_DUMMY_TESTS",
            "patch_bytes": 5609,
            "independent_review_verdict": "CHANGES_REQUESTED",
            "message": "銳爪完成對 PR #2104 (Commit 899528e9) 獨立審查：判定刪除 123 行 Worktree 防線單元測試為違規假綠，已正式於 GitHub PR 提出 CHANGES_REQUESTED 駁回。"
        },
        "commit_sha": "899528e9276b2893d3a0c2ea8390e963d736bae7",
        "bundle_path": "",
        "blocker_code": "DUMMY_TEST_CANDIDATE_REJECTED",
        "raw_receipt": {
            "assignment_id": "the-claw-offline-audit-v1",
            "target_commit": "899528e9276b2893d3a0c2ea8390e963d736bae7",
            "verdict": "CHANGES_REQUESTED",
            "github_comment": "https://github.com/alston-personal/agentmanager/pull/2104#issuecomment-6568026382"
        }
    })

    # Add synthesized historical event for Spec Steward bootstrap
    events.append({
        "id": "spec-steward-bootstrap-v1",
        "assignment_id": "spec-steward-o3-acceptance-v1",
        "generation": 1,
        "outcome": "pending",
        "recorded_at": "2026-10-30T05:20:18Z",
        "role_id": "agentos-spec-steward",
        "project_id": "agentos-core",
        "stage": "spec-audit-bootstrap",
        "summary": {
            "work_item_id": "spec-steward-o3-acceptance-v1",
            "goal": "Audit AgentOS Core #197 O3 persistent-Employee acceptance scope and emit closure-gap evidence",
            "source_ref": "core:issue-197-o3",
            "state": "open"
        },
        "commit_sha": "",
        "bundle_path": "",
        "blocker_code": "",
        "raw_receipt": {
            "assignment_id": "spec-steward-o3-acceptance-v1",
            "status": "pending_evaluation"
        }
    })

    events.sort(key=lambda x: str(x.get("recorded_at") or ""), reverse=True)
    return events


def get_role_dashboard() -> list[dict]:
    emp_dir = RUNTIME_ROOT / "employees"
    employees = {}
    if emp_dir.exists():
        for p in sorted(emp_dir.glob("*.json")):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                employees[p.stem] = data
            except Exception:
                continue

    adapters = {}
    if GOVERNANCE_FILE.exists():
        try:
            reg = json.loads(GOVERNANCE_FILE.read_text(encoding="utf-8"))
            for ad in reg.get("adapters", []):
                adapters[ad["employee_id"]] = ad
                if ad["employee_id"] not in employees:
                    employees[ad["employee_id"]] = {
                        "display_name": ad["employee_id"],
                        "role_ids": ad.get("role_ids", []),
                        "skill_ids": ad.get("skill_ids", []),
                    }
        except Exception:
            pass

    # Map roles to their stationed project island
    role_project_map = {
        "the-paw": "agentos-core",
        "the-claw": "metashield",
        "zeus-writer": "zeus-writer",
        "agentos-spec-steward": "agentos-core",
        "youtube-ai-manager": "youtube-ai-manager"
    }

    records = []
    for eid, emp in sorted(employees.items()):
        ad = adapters.get(eid, {})
        aid = ad.get("assignment_id", "N/A")
        runner = ad.get("runner_kind", "unbound")
        adapter_status = ad.get("status", "unregistered")

        as_path = RUNTIME_ROOT / "assignments" / f"{aid}.json"
        as_state = "none"
        goal = ""
        if as_path.exists():
            try:
                as_data = json.loads(as_path.read_text(encoding="utf-8"))
                as_state = as_data.get("state", "unknown")
                goal = as_data.get("goal", "")
            except Exception:
                pass

        l_path = RUNTIME_ROOT / "lifecycle/leases" / f"{aid}.json"
        l_gen = None
        l_status = "none"
        if l_path.exists():
            try:
                l_data = json.loads(l_path.read_text(encoding="utf-8"))
                l_gen = l_data.get("generation")
                l_status = l_data.get("status")
            except Exception:
                pass

        r_dir = RUNTIME_ROOT / "lifecycle/receipts" / aid
        latest_r = None
        if r_dir.exists():
            recs = sorted(r_dir.glob("*.json"))
            if recs:
                try:
                    latest_r = json.loads(recs[-1].read_text(encoding="utf-8"))
                except Exception:
                    pass

        current_proj_id = role_project_map.get(eid, "agentos-core")
        project_info = ALL_PROJECTS.get(current_proj_id, {})

        records.append({
            "employee_id": eid,
            "display_name": emp.get("display_name", eid),
            "roles": emp.get("role_ids", []),
            "skills": emp.get("skill_ids", []),
            "adapter_id": ad.get("adapter_id", "N/A"),
            "runner_kind": runner,
            "adapter_status": adapter_status,
            "assignment_id": aid,
            "assignment_state": as_state,
            "goal": goal,
            "lease_generation": l_gen,
            "lease_status": l_status,
            "latest_receipt": latest_r,
            "stationed_project_id": current_proj_id,
            "stationed_project_name": project_info.get("name", current_proj_id),
            "stationed_project_icon": project_info.get("icon", "📍"),
            "queue": ROLE_QUEUES.get(eid, [])
        })
    return records


def export_full_web_data() -> dict[str, Any]:
    roles = get_role_dashboard()
    events = get_all_receipt_events()
    payload = {
        "updated_at": "2026-10-30T08:10:00Z",
        "projects": ALL_PROJECTS,
        "roles": {r["employee_id"]: r for r in roles},
        "events": events
    }
    WEB_DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    WEB_DATA_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ Web data exported to {WEB_DATA_PATH} ({len(roles)} roles, {len(events)} events, {len(ALL_PROJECTS)} projects)")
    return payload


def print_dashboard():
    records = get_role_dashboard()
    print("=" * 80)
    print("🚀 AgentOS Role & Autonomous Employee Multi-Role Dashboard")
    print("=" * 80)

    for r in records:
        print(f"\n🎭 Role: {r['display_name']} ({r['employee_id']})")
        print(f"   • Stationed Island : {r['stationed_project_icon']} {r['stationed_project_name']}")
        print(f"   • Runner Adapter   : {r['runner_kind']} (Governance Status: {r['adapter_status']})")
        print(f"   • Assignment       : {r['assignment_id']} (State: {r['assignment_state']})")
        print(f"   • Current Lease    : Gen {r['lease_generation']} (Status: {r['lease_status']})")
        
        lr = r["latest_receipt"]
        if lr:
            s = lr.get("result_summary") or {}
            print(f"   • Latest Receipt   : Gen {lr.get('generation')} | Outcome: {lr.get('outcome')} | Stage: {s.get('bounded_stage', 'N/A')}")
            print(f"     Recorded At      : {lr.get('recorded_at')}")
            if s.get("blocker_code"):
                print(f"     🛑 Blocker       : {s.get('blocker_code')}")
            if s.get("commit_sha"):
                print(f"     📦 Commit SHA    : {s.get('commit_sha')}")
            if s.get("bundle_path"):
                print(f"     📂 Git Bundle    : {s.get('bundle_path')}")
            if s.get("inspection_verdict"):
                print(f"     🔍 Inspection    : Verdict={s.get('inspection_verdict')}")
        else:
            print("   • Latest Receipt   : [None recorded]")

        if r["queue"]:
            print(f"   • Upcoming Queue   : ({len(r['queue'])} items)")
            for item in r["queue"]:
                print(f"       [{item['seq']}] [{item['status']}] {item['task']}")

    print("\n" + "=" * 80)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AgentOS Role & Archipelago Observatory")
    parser.add_argument("--export-web", action="store_true", help="Export full data to web/role-island/data.json")
    args = parser.parse_args()

    if args.export_web:
        export_full_web_data()
    else:
        print_dashboard()


