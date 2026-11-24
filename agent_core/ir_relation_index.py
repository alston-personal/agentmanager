#!/usr/bin/env python3
"""
IR Relation Index & Dynamic Lazy Projection (IR-INDEX-01, IR-INDEX-02)
----------------------------------------------------------------------
為 AgentOS ONE Canonical IR 提供概念拓撲索引與動態按需投影能力：
1. 概念萃取與關聯圖譜 (Concept Extraction & Linking):
   - 將沉澱在 continuity/*.json、execution-head.json 中的歷史 decisions、evidence、goals 萃取為概念節點。
   - 建立 IR 與 Concept 之間的關聯邊 (Edge)，支援跨專案智慧關聯與湧現 (Emergence)。
2. 骨架與動態投影 (Skeleton & Dynamic Projection):
   - 解決每次對話開局「全量硬塞」吃爆上下文 Token 的痛點。
   - 產生輕量骨架：當前目標 (Active Goal) + 首要待辦 (pending_tasks[0]) + 動態召回最相關的 Top-K 歷史決策。
   - 支援依據當前任務意圖 (query_text) 進行語意/概念按需召回 (Recall-before-Act)。
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

IR_GRAPH_SCHEMA = "agentos.ir-relation-graph/v1"

# 跨專案核心概念辭典 (可隨系統演進擴充)
IR_CONCEPTS: dict[str, tuple[str, ...]] = {
    "web_routing_and_gateway": ("nginx", "403", "http 200", "curl", "dns", "gateway", "reverse proxy", "port"),
    "security_and_credentials": ("api key", "secret", "0600", "chmod", "privacy", "detect-secrets", "token", "leak"),
    "dynamic_models": ("model_catalog", "gpt-6", "gemini thinking", "dual_agent", "inference_strength", "consensus"),
    "editorial_and_consistency": ("zeus", "小說", "章節", "矛盾", "審批", "反白", "inline annotation", "改寫", "consistency"),
    "worktree_and_concurrency": ("worktree", "pawclonepool", "parallel", "lock", "clone", "isolation"),
    "governance_and_preflight": ("constitution", "preflight", "protected_branch", "guard", "doc-code", "reality"),
    "persona_and_continuation": ("persona", "character_ir", "canonical_ir", "continuation", "avatar", "mcp", "thin client"),
    "qa_and_automation": ("redmine", "testrail", "confluence", "monthly_report", "scriptless", "issue draft"),
}

def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

def extract_ir_concepts(text: str) -> list[str]:
    lower = text.lower()
    matched = []
    for concept, kws in IR_CONCEPTS.items():
        if any(kw in lower for kw in kws):
            matched.append(concept)
    return matched

def build_ir_relation_graph(data_root: Path) -> dict[str, Any]:
    """掃描所有專案的 continuity/*.json 與 execution-head.json，構建 IR 拓撲圖譜。"""
    root = Path(data_root).resolve()
    projects_dir = root / "projects"
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []

    def add_node(nid: str, kind: str, title: str, ref: str, summary: str = "", metadata: dict = None) -> None:
        if nid not in nodes:
            nodes[nid] = {
                "id": nid,
                "kind": kind,
                "title": title,
                "raw_ref": ref,
                "summary": summary[:280],
                "metadata": metadata or {}
            }

    def add_edge(src: str, dst: str, rel: str) -> None:
        edges.append({"source": src, "target": dst, "relation": rel})

    if projects_dir.is_dir():
        for proj in sorted(projects_dir.glob("*")):
            if not proj.is_dir():
                continue
            pname = proj.name
            cont_dir = proj / "continuity"
            head_file = proj / "execution-head.json"

            # 1. 索引 execution-head.json
            if head_file.is_file():
                try:
                    head_data = json.loads(head_file.read_text(encoding="utf-8"))
                    goal = head_data.get("active_goal") or head_data.get("goal") or ""
                    hid = f"head:{pname}"
                    add_node(hid, "execution_head", f"Goal of {pname}", f"projects/{pname}/execution-head.json", summary=goal)
                    for c in extract_ir_concepts(goal):
                        cid = f"concept:{c}"
                        add_node(cid, "concept", c, "concepts")
                        add_edge(hid, cid, "targets_concept")
                except Exception:
                    pass

            # 2. 索引 continuity 中的各代 canonical IR
            if cont_dir.is_dir():
                for cfile in sorted(cont_dir.glob("*.json")):
                    try:
                        cdata = json.loads(cfile.read_text(encoding="utf-8"))
                        cir = cdata.get("canonical_ir") or cdata
                        decisions = cir.get("decisions", [])
                        for idx, dec in enumerate(decisions):
                            did = f"decision:{pname}:{idx}"
                            add_node(did, "decision", f"{pname} Dec #{idx}", f"projects/{pname}/continuity/{cfile.name}#decisions[{idx}]", summary=dec)
                            for c in extract_ir_concepts(dec):
                                cid = f"concept:{c}"
                                add_node(cid, "concept", c, "concepts")
                                add_edge(did, cid, "relates_to_concept")
                    except Exception:
                        pass

    graph = {
        "schema": IR_GRAPH_SCHEMA,
        "indexer_version": "1.0.0",
        "rebuilt_at": _utc_now(),
        "stats": {
            "node_count": len(nodes),
            "edge_count": len(edges),
        },
        "nodes": list(nodes.values()),
        "edges": edges,
    }

    out_file = root / "knowledge" / "ir_relation_graph.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(graph, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return graph

def load_or_rebuild_ir_graph(data_root: Path) -> dict[str, Any]:
    out_file = Path(data_root).resolve() / "knowledge" / "ir_relation_graph.json"
    if out_file.is_file():
        try:
            d = json.loads(out_file.read_text(encoding="utf-8"))
            if d.get("schema") == IR_GRAPH_SCHEMA:
                return d
        except Exception:
            pass
    return build_ir_relation_graph(data_root)

def project_canonical_ir(
    raw_ir: dict[str, Any],
    query_intent: str = "",
    data_root: Optional[Path] = None,
    max_recalled_decisions: int = 4
) -> dict[str, Any]:
    """
    動態骨架投影：
    將龐大的 Canonical IR 精煉為「極簡骨架 + 意圖關聯召回決策 + 首要待辦」。
    大幅降低開局 Token 消耗並促成智慧湧現。
    """
    all_decisions = raw_ir.get("decisions", [])
    pending_tasks = raw_ir.get("pending_tasks", [])
    active_goal = raw_ir.get("goal") or raw_ir.get("continuation", {}).get("next_action") or ""

    # 若無指定 data_root 則使用預設
    root = data_root or Path("/home/ubuntu/agent-data")
    graph = load_or_rebuild_ir_graph(root)

    # 依據意圖進行概念檢索
    query_concepts = set(extract_ir_concepts(f"{query_intent} {active_goal}"))
    recalled_decisions = []

    if query_concepts and graph.get("edges"):
        # 尋找匹配概念的決策
        matched_decision_ids = set()
        for edge in graph["edges"]:
            tgt = edge["target"]
            if tgt.startswith("concept:") and tgt.split(":", 1)[1] in query_concepts:
                if edge["source"].startswith("decision:"):
                    matched_decision_ids.add(edge["source"])

        nodes_by_id = {n["id"]: n for n in graph.get("nodes", [])}
        for did in matched_decision_ids:
            if did in nodes_by_id:
                recalled_decisions.append(nodes_by_id[did]["summary"])
                if len(recalled_decisions) >= max_recalled_decisions:
                    break

    # 若關聯召回不足，則取最新 2 筆兜底
    if len(recalled_decisions) < 2 and all_decisions:
        for d in all_decisions[-2:]:
            if d not in recalled_decisions:
                recalled_decisions.append(d)

    projected_ir = {
        "schema_version": "agentos.projected-ir/v1",
        "projection_mode": "dynamic_lazy_hydrated",
        "project_id": raw_ir.get("project_id", "agentos-core"),
        "index_id": raw_ir.get("index_id"),
        "ir_id": raw_ir.get("ir_id"),
        "active_goal": active_goal,
        "next_action": raw_ir.get("next_action") or raw_ir.get("continuation", {}).get("next_action"),
        # 嚴格落實 One-Pending-Task-Per-Turn，只投影第一項
        "current_task": pending_tasks[0] if pending_tasks else None,
        "total_pending_count": len(pending_tasks),
        # 智能動態召回相關決策，而非死塞幾十條
        "recalled_relevant_decisions": recalled_decisions,
        "total_historical_decisions_archived": len(all_decisions),
    }

    return projected_ir

if __name__ == "__main__":
    root = Path("/home/ubuntu/agent-data")
    g = build_ir_relation_graph(root)
    print(f"✅ IR Relation Graph built: {g['stats']['node_count']} nodes, {g['stats']['edge_count']} edges")

    # 模擬測試：針對「小說審核反白與前後文矛盾」進行動態投影
    with open(root / "projects/agentos-core/continuity/latest.json") as f:
        raw = json.load(f).get("canonical_ir", {})

    proj = project_canonical_ir(raw, query_intent="小說審批與前後文矛盾反白")
    print("\n=== Dynamic Projected IR (骨架與按需投影) ===")
    print(json.dumps(proj, indent=2, ensure_ascii=False))
