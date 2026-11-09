#!/usr/bin/env python3
"""AgentOS Codebase Atlas & Semantic Index Engine.

Provides persistent, machine-readable file and topic indexing so that:
1. File investigations and search traces are never discarded or repeated needlessly.
2. Agents can instantly query 'which file contains what information' without scanning disks.
3. File digests are cached with SHA256 hashes to prevent redundant I/O.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

AGENTMANAGER_ROOT = Path("/home/ubuntu/agentmanager")
DATA_ROOT = Path(os.environ.get("AGENT_DATA_ROOT", "/home/ubuntu/agent-data"))
INDEX_DIR = DATA_ROOT / "indexes"
TOPIC_MAP_PATH = INDEX_DIR / "topic_routing_map.json"
FILE_CATALOG_PATH = INDEX_DIR / "file_catalog.json"
SEARCH_TRACE_PATH = INDEX_DIR / "search_trace_cache.json"

SCHEMA_TOPIC = "agentos.atlas-topic-map/v1"
SCHEMA_CATALOG = "agentos.atlas-file-catalog/v1"
SCHEMA_TRACE = "agentos.atlas-search-trace/v1"


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    if not path.is_file():
        return ""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def ensure_index_dir():
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    if not TOPIC_MAP_PATH.exists():
        TOPIC_MAP_PATH.write_text(json.dumps({
            "schema": SCHEMA_TOPIC,
            "updated_at": now_utc(),
            "topics": {}
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not FILE_CATALOG_PATH.exists():
        FILE_CATALOG_PATH.write_text(json.dumps({
            "schema": SCHEMA_CATALOG,
            "updated_at": now_utc(),
            "files": {}
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not SEARCH_TRACE_PATH.exists():
        SEARCH_TRACE_PATH.write_text(json.dumps({
            "schema": SCHEMA_TRACE,
            "updated_at": now_utc(),
            "traces": []
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_json(path: Path) -> dict[str, Any]:
    ensure_index_dir()
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_json(path: Path, data: dict[str, Any]):
    ensure_index_dir()
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


# Core Atlas Locator: Match query against Topics, File Catalog, and Search Traces
def scan_directory(target_dir: Path | None = None) -> dict[str, int]:
    """Incrementally scan python files, extract docstrings/symbols, cache SHA256."""
    ensure_index_dir()
    catalog_data = load_json(FILE_CATALOG_PATH)
    files_map = catalog_data.setdefault("files", {})

    target_dir = target_dir or AGENTMANAGER_ROOT
    scanned = 0
    updated = 0
    skipped = 0

    scan_roots = [
        target_dir / "scripts",
        target_dir / "agent_core",
        target_dir / "agentos_node"
    ]

    for root in scan_roots:
        if not root.exists():
            continue
        for p in root.rglob("*.py"):
            if "__pycache__" in str(p) or "/." in str(p):
                continue
            scanned += 1
            rel_path = str(p.relative_to(AGENTMANAGER_ROOT)) if p.is_relative_to(AGENTMANAGER_ROOT) else str(p)
            current_sha = sha256_file(p)

            # Incremental check: Skip if hash unchanged
            cached_entry = files_map.get(rel_path)
            if cached_entry and cached_entry.get("sha256") == current_sha:
                skipped += 1
                continue

            # Parse AST for docstrings and exported symbols
            purpose = ""
            symbols = []
            try:
                content = p.read_text(encoding="utf-8")
                tree = ast.parse(content, filename=str(p))
                doc = ast.get_docstring(tree)
                if doc:
                    purpose = doc.strip().split("\n")[0][:120]
                for node in ast.iter_child_nodes(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                        if not node.name.startswith("_"):
                            symbols.append(node.name)
            except Exception as e:
                purpose = f"Parsing error: {e}"

            files_map[rel_path] = {
                "sha256": current_sha,
                "purpose": purpose or f"Python module: {p.name}",
                "symbols": symbols[:12],
                "last_scanned_at": now_utc(),
                "size_bytes": p.stat().st_size
            }
            updated += 1

    catalog_data["updated_at"] = now_utc()
    save_json(FILE_CATALOG_PATH, catalog_data)
    return {"scanned": scanned, "updated": updated, "skipped": skipped}


def get_status() -> dict[str, Any]:
    ensure_index_dir()
    topic_data = load_json(TOPIC_MAP_PATH)
    file_data = load_json(FILE_CATALOG_PATH)
    trace_data = load_json(SEARCH_TRACE_PATH)

    return {
        "topics_count": len(topic_data.get("topics", {})),
        "files_indexed": len(file_data.get("files", {})),
        "traces_cached": len(trace_data.get("traces", [])),
        "topics_updated_at": topic_data.get("updated_at"),
        "catalog_updated_at": file_data.get("updated_at"),
        "traces_updated_at": trace_data.get("updated_at"),
    }


# Core Atlas Locator: Match query against Topics, File Catalog, and Search Traces
def locate(query: str, limit: int = 5) -> list[dict[str, Any]]:
    ensure_index_dir()
    tokens = [t.lower() for t in re.split(r"[\s,;_\-/]+", query) if len(t) >= 2]
    if not tokens:
        return []

    topic_data = load_json(TOPIC_MAP_PATH)
    file_data = load_json(FILE_CATALOG_PATH)
    trace_data = load_json(SEARCH_TRACE_PATH)

    matches = []

    # 1. Search Traces first (Highest value: previously solved investigations)
    for trace in trace_data.get("traces", []):
        t_query = str(trace.get("query", "")).lower()
        score = sum(2 for t in tokens if t in t_query)
        if score > 0:
            matches.append({
                "type": "trace_hit",
                "score": score + 3,
                "title": f"歷史檢索命中: {trace.get('query')}",
                "summary": trace.get("answer_summary", ""),
                "primary_files": trace.get("files", []),
                "reusable_facts": trace.get("reusable_facts", {})
            })

    # 2. Search Topics
    for topic_id, t_info in topic_data.get("topics", {}).items():
        search_blob = (topic_id + " " + t_info.get("name", "") + " " + t_info.get("summary", "") + " " + " ".join(t_info.get("keywords", []))).lower()
        score = sum(1 for t in tokens if t in search_blob)
        if score > 0:
            matches.append({
                "type": "topic_routing",
                "score": score + 2,
                "topic_id": topic_id,
                "title": f"主題路由: {t_info.get('name', topic_id)}",
                "summary": t_info.get("summary", ""),
                "primary_files": t_info.get("primary_files", []),
                "data_files": t_info.get("data_files", []),
                "canonical_anchors": t_info.get("anchors", {})
            })

    # 3. Search File Catalog
    for rel_path, f_info in file_data.get("files", {}).items():
        search_blob = (rel_path + " " + f_info.get("purpose", "") + " " + " ".join(f_info.get("symbols", []))).lower()
        score = sum(1 for t in tokens if t in search_blob)
        if score > 0:
            matches.append({
                "type": "file_catalog_hit",
                "score": score,
                "title": f"檔案索引: {rel_path}",
                "summary": f_info.get("purpose", ""),
                "primary_files": [rel_path],
                "exports": f_info.get("symbols", [])[:5]
            })

    matches.sort(key=lambda x: x["score"], reverse=True)
    return matches[:limit]


# Record Search Trace: "Don't make searches a single-use waste"
def record_trace(query: str, answer_summary: str, files: list[str], facts: dict[str, Any] | None = None):
    ensure_index_dir()
    trace_data = load_json(SEARCH_TRACE_PATH)
    traces = trace_data.setdefault("traces", [])

    entry = {
        "id": f"trace_{int(time.time())}_{hashlib.md5(query.encode()).hexdigest()[:6]}",
        "created_at": now_utc(),
        "query": query.strip(),
        "answer_summary": answer_summary.strip(),
        "files": files,
        "reusable_facts": facts or {}
    }
    # Keep traces bounded (latest 200 high-value traces)
    traces.insert(0, entry)
    trace_data["traces"] = traces[:200]
    trace_data["updated_at"] = now_utc()
    save_json(SEARCH_TRACE_PATH, trace_data)
    print(f"✅ Search trace successfully crystallized: '{query[:40]}...' -> {len(files)} file(s)")


# Auto Index Core Architecture Topics
def bootstrap_core_topics():
    ensure_index_dir()
    data = load_json(TOPIC_MAP_PATH)
    topics = data.setdefault("topics", {})

    canonical_topics = {
        "ports_and_networking": {
            "name": "系統連接埠與反向代理劃分",
            "summary": "全系統監聽連接埠、Nginx 反向代理、SSL 與獨立服務映射總表",
            "keywords": ["port", "連接埠", "nginx", "proxy", "反向代理", "8768", "8776", "3003", "8780", "443"],
            "primary_files": ["agentmanager/scripts/core_services/port_manager.py", "/etc/nginx/sites-available/studio.milkcat.org"],
            "data_files": ["agent-data/resources/registry.json"],
            "anchors": {
                "3003": "mio-intel-hub (Threads 情報收集與候選庫 API)",
                "8768": "milkcat-credits (虛擬點數與記帳服務)",
                "8776": "teams-commander (Teams 橋接控制台)",
                "8780": "realm-fabric (AgentOS ONE 跨節點核心通訊)"
            }
        },
        "mio_social_and_persona": {
            "name": "澪 (Mio) 社群自治與人設成長",
            "summary": "Mio 的 Threads 貼文發佈、回覆決策、去重同步、人設 IR 演化與自然語調過濾",
            "keywords": ["mio", "threads", "persona", "人設", "反ai腔", "社群", "回覆", "去重"],
            "primary_files": [
                "agentmanager/scripts/mio_persona_social_loop_user.py",
                "agentmanager/scripts/sync_sunlake_milkcat_persona_user.py",
                "agentmanager/scripts/evolve_mio_persona_ir_user.py",
                "agentmanager/scripts/threads_intel_crawler.py"
            ],
            "data_files": [
                "agent-data/personas/sunlake-milkcat/ir/current.json",
                "agent-data/personas/sunlake-milkcat/events/events.jsonl",
                "agent-data/personas/sunlake-milkcat/reply_policy.json",
                "agent-data/personas/sunlake-milkcat/intel_candidates.json"
            ],
            "anchors": {
                "events.jsonl": "歷史事件串流（包含已發佈貼文與回覆）",
                "ir/current.json": "規範性 Persona IR（最新 Revision 122）",
                "reply_policy.json": "防 AI 腔調指令與情緒節律閥值"
            }
        },
        "character_fusion_pipeline": {
            "name": "角色特徵融合 (Character Fusion)",
            "summary": "將人物外觀特徵融合至吉祥物/水滴等主體之渲染工作流與品質審查",
            "keywords": ["fusion", "character", "mascot", "water_drop", "吉祥物", "水滴", "pollinations", "qwen"],
            "primary_files": [
                "agentmanager/scripts/character_fusion_worker.py",
                "agentmanager/scripts/character_fusion_live_smoke_user.sh"
            ],
            "data_files": ["agent-data/releases/character-fusion/"],
            "anchors": {
                "water_drop_body_plan": "非人形純水滴本體形態嚴格防護",
                "render_fallbacks": "HF -> Qwen -> Pollinations Flux -> Flow Web"
            }
        },
        "realm_nodes_and_ota": {
            "name": "跨主機節點管理與 OTA 自癒",
            "summary": "分散式節點註冊 (Node Registry)、Thin Client 部署、心跳監控與遠端 OTA 版本收斂",
            "keywords": ["node", "thin_client", "realm", "ota", "節點", "mbpr", "vopc5750", "vo10005870"],
            "primary_files": [
                "agentmanager/agent_core/runtime_ota.py",
                "agentmanager/agent_core/controller_api.py",
                "agentmanager/agentos_node/thin_client.py",
                "agentmanager/docs/NODE_MIGRATION_PLAYBOOK.md"
            ],
            "data_files": ["agent-data/realm/nodes.json", "agent-data/realm/runtime-ota.json"],
            "anchors": {
                "nodes.json": "全域節點清單與上線狀態",
                "install-agentos.ps1": "Windows 節點一鍵升級與守護排程腳本"
            }
        },
        "role_reality_and_pdca": {
            "name": "角色真實性守門與自治運轉 (Role Reality & PDCA)",
            "summary": "杜絕紙面空殼角色的現實守門盾 (Role Reality Guard) 與全角色自治推動器",
            "keywords": ["role", "pdca", "the_paw", "the_claw", "atlast", "hermes", "cerberus", "憑證", "空殼"],
            "primary_files": [
                "agentmanager/scripts/role_reality_guard.py",
                "agentmanager/scripts/role_pdca_runner.py",
                "agentmanager/scripts/sync_mission_control.py",
                "agentmanager/scripts/sync_persona_portal.py"
            ],
            "data_files": ["agent-data/personas/"],
            "anchors": {
                "role_reality_guard.py": "即時稽核實體目錄、代碼與執行憑證",
                "sync_persona_portal.py": "AI 角色神殿 (studio.milkcat.org/personas/) 雙層靜態發布"
            }
        }
    }

    for k, v in canonical_topics.items():
        topics[k] = v
        topics[k]["indexed_at"] = now_utc()

    data["topics"] = topics
    data["updated_at"] = now_utc()
    save_json(TOPIC_MAP_PATH, data)
    print(f"✅ Initialized {len(canonical_topics)} core architecture topics in Atlas.")


def main():
    parser = argparse.ArgumentParser(description="AgentOS Codebase Atlas & Semantic Index Engine")
    sub = parser.add_subparsers(dest="cmd")

    p_locate = sub.add_parser("locate", help="Locate files and relevant context for a query")
    p_locate.add_argument("query", help="Natural language query or keywords")
    p_locate.add_argument("--limit", type=int, default=5)

    p_record = sub.add_parser("record", help="Record a search trace to prevent repeated investigation waste")
    p_record.add_argument("--query", required=True, help="Investigation question")
    p_record.add_argument("--answer", required=True, help="Concise finding or answer")
    p_record.add_argument("--files", nargs="+", required=True, help="Primary files involved")

    p_scan = sub.add_parser("scan", help="Incrementally scan codebase to update file catalog")
    p_scan.add_argument("--dir", default=None, help="Target directory (defaults to agentmanager)")

    p_status = sub.add_parser("status", help="Show current Atlas index statistics")

    p_init = sub.add_parser("init", help="Bootstrap core topics in Atlas")

    args = parser.parse_args()

    if args.cmd == "status":
        st = get_status()
        print("\n📊 AgentOS Atlas 經緯圖統計：")
        print(f"  • 主題路由數 (Topics): {st['topics_count']} (更新時間: {st['topics_updated_at']})")
        print(f"  • 檔案索引數 (Files) : {st['files_indexed']} (更新時間: {st['catalog_updated_at']})")
        print(f"  • 檢索結晶數 (Traces): {st['traces_cached']} (更新時間: {st['traces_updated_at']})")

    elif args.cmd == "scan":
        target = Path(args.dir) if args.dir else AGENTMANAGER_ROOT
        print(f"🔄 開始對 {target} 執行增量代碼經緯掃描...")
        res = scan_directory(target)
        print(f"✅ 掃描完成！掃描檔案: {res['scanned']}, 更新: {res['updated']}, 未變動跳過: {res['skipped']}")

    elif args.cmd == "locate":
        results = locate(args.query, limit=args.limit)
        if not results:
            print(f"🔍 未在 Atlas 索引中找到與 '{args.query}' 直接相關的主題或歷史軌跡。建議進行精確檔案探查後使用 'record' 沉澱。")
            return
        print(f"\n🗺️  AgentOS Atlas 經緯導航結果 ({len(results)} 項命中)：")
        print("=" * 65)
        for idx, r in enumerate(results, 1):
            print(f"[{idx}] {r['title']} (信心度: {r['score']})")
            print(f"    💡 摘要: {r['summary']}")
            if r.get("primary_files"):
                print(f"    📂 優先探查檔案: {', '.join(r['primary_files'])}")
            if r.get("canonical_anchors"):
                for ak, av in list(r["canonical_anchors"].items())[:3]:
                    print(f"       ⚓ {ak}: {av}")
            print("-" * 65)

    elif args.cmd == "record":
        record_trace(args.query, args.answer, args.files)

    elif args.cmd == "init":
        bootstrap_core_topics()

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
