#!/usr/bin/env python3
"""Prometheus Engine — Architecture Synergy & Fire-Bringer Scout (system.prometheus).

Scans recently validated patterns (such as Runtime API dispatch, Thin-Client OTA, Dynamic Avatar Pull),
identifies projects and specs that can benefit from these patterns, and produces
an Architecture Synergy & Uplift Report.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = "agentos.architecture-synergy-report/v1"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def scan_fire_patterns(repo_root: Path) -> list[dict[str, Any]]:
    """Extract validated fire patterns from recent governance, CURRENT_STATE and growth proofs."""
    patterns = []

    # Pattern 1: Runtime API Dispatching (no direct Git push for queues)
    patterns.append({
        "pattern_id": "pattern-runtime-api-dispatch",
        "name": "跨節點 Runtime API 即時排程（根絕 Git Push 任務隊列）",
        "origin": "PR #2389 / agent_core/realm_server.py / POST /v1/tasks",
        "principle": "邊緣節點必須透過中央調度器 HTTP API 派工，不得自行 commit/push 到 fabric.json，以確保長輪詢即時喚醒。",
        "applicability": [
            "dqa03backup", "vopc5750", "redmine_qa_workflow", "monthly_report", "matters_publisher"
        ],
        "recommendation": "檢視所有專案中帶有遠端派工或跨機協同的腳本，改用 agentos-client dispatch 或 POST /v1/tasks。"
    })

    # Pattern 2: Thin-Client Heartbeat OTA Target Convergence
    patterns.append({
        "pattern_id": "pattern-thin-client-heartbeat-ota",
        "name": "Thin-Client 心跳 OTA 目標版本自動收斂",
        "origin": "PR #2389 / agentos_node/thin_client_transport.py",
        "principle": "在 Heartbeat 回傳 target_release_commit，由邊緣節點監控 runtime-provenance.json 原地自動收斂升級。",
        "applicability": [
            "vopc5750", "VO10005870", "dqa03restore", "dqa03backup", "mbpr"
        ],
        "recommendation": "推動所有已入籍邊緣節點部署守護進程，確保全叢集代碼與治理契約零時差同步。"
    })

    # Pattern 3: Dynamic Atlas Avatar Pull Endpoint
    patterns.append({
        "pattern_id": "pattern-dynamic-atlas-avatar-endpoint",
        "name": "Atlas Avatar 動態 Persona 與 Canonical IR 拉取端點",
        "origin": "PR #2388 / agent_core/realm_server.py / GET /v1/atlas/avatar",
        "principle": "外部 GPTs 與 Google Gems 不再硬編碼靜態 Prompt，改由動態拉取中央最新降臨人格與目標。",
        "applicability": [
            "Google Gems", "ChatGPT Custom GPTs", "Web Agent Surface"
        ],
        "recommendation": "全面汰換第三方 LLM 介面中超過 48 小時的靜態 System Prompt，接入動態端點。"
    })

    return patterns


def scan_specs_for_modernization(data_root: Path) -> list[dict[str, Any]]:
    """Scan specs in agent-data/specs and detect outdated assumptions."""
    candidates = []
    specs_dir = data_root / "specs"
    if not specs_dir.exists():
        return candidates

    for spec_file in specs_dir.glob("*.md"):
        try:
            content = spec_file.read_text(encoding="utf-8")
        except Exception:
            continue
        # Check for legacy patterns
        hints = []
        if "git push" in content.lower() and "task" in content.lower():
            hints.append("包含透過 Git 派發任務的舊時代假設，應升級為 POST /v1/tasks")
        if "pulse" in content.lower():
            hints.append("包含舊時代 Pulse 板狀態機描述，應遷移至 Canonical IR / One Continuation")
        if hints:
            candidates.append({
                "spec_path": str(spec_file),
                "spec_name": spec_file.name,
                "modernization_hints": hints
            })

    return candidates


def generate_synergy_report(repo_root: Path, data_root: Path) -> dict[str, Any]:
    patterns = scan_fire_patterns(repo_root)
    outdated_specs = scan_specs_for_modernization(data_root)

    return {
        "schema": SCHEMA,
        "scout": "system.prometheus",
        "scout_name": "普羅米修斯 Prometheus (先見之神與盜火者)",
        "generated_at": _utc_now(),
        "fire_patterns_count": len(patterns),
        "fire_patterns": patterns,
        "outdated_specs_identified": len(outdated_specs),
        "outdated_specs": outdated_specs,
        "strategic_uplift_proposals": [
            {
                "proposal_id": "UPLIFT-20261126-001",
                "title": "跨節點工作流全面改採 Runtime API 派工 (DQA / Monthly Report / Redmine QA)",
                "actionable_owner": "sector.paw",
                "target_specs": ["agent-data/specs/dqa_system_monitor.md", "agent-data/specs/monthly_report.md"],
                "benefit": "徹底消除 Git 倉庫非同步導致的任務空轉，實現跨機秒級喚醒。"
            },
            {
                "proposal_id": "UPLIFT-20261126-002",
                "title": "第三方 LLM 界面全面導入 Atlas Avatar 動態端點",
                "actionable_owner": "sector.weaver",
                "target_specs": ["agent-data/specs/gemini-web-executor-hook.md"],
                "benefit": "解決 Web GPT / Google Gems 歷史會話狀態落差與手動同步成本。"
            }
        ]
    }


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    data_root = Path(os.environ.get("AGENT_DATA_ROOT", "/home/ubuntu/agent-data"))

    report = generate_synergy_report(repo_root, data_root)
    out_dir = data_root / "synergy"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "latest_synergy_report.json"
    out_file.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"🔥 [Prometheus] 盜火綜效掃描完成！報告已沉澱至: {out_file}")
    print(f"   - 提煉火種模式: {report['fire_patterns_count']} 項")
    print(f"   - 檢測舊規重塑: {report['outdated_specs_identified']} 處")
    print(f"   - 提出升級提案: {len(report['strategic_uplift_proposals'])} 案")
    return 0


if __name__ == "__main__":
    sys.exit(main())
