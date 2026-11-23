"""Evolvable Knowledge Relation Index & Recall-before-Act (KG-LINK-01, KG-LINK-02).

Design principle (Immutable Raw Data + Evolvable Index Layer):
- Raw data under $AGENT_DATA_ROOT (projects/*/STATUS.md, personas/*/pitfalls_guardrails.md,
  personas/*/consolidated_experiences.jsonl, evidence/*.json) is strictly READ-ONLY.
- The upper-layer relation graph ($AGENT_DATA_ROOT/knowledge/relation_graph.json) is a
  versioned, rebuildable projection whose nodes and edges always carry `raw_ref` pointers
  back to the exact raw data file/line/record.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


GRAPH_SCHEMA = "agentos.relation-graph/v1"
INDEXER_VERSION = "1.0.0"

_CONCEPT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "character_ir": ("character ir", "character_ir", "ir snapshot", "fork_persona", "mio", "persona"),
    "inline_annotation": ("反白", "註解", "annotation", "issue draft", "審批"),
    "nginx_http_verify": ("nginx", "403", "http 200", "curl", "mission-control"),
    "worktree_parallel": ("worktree", "pawclonepool", "分靈體", "clone", "lock"),
    "market_prediction": ("預測", "實盤", "market", "prediction", "覆盤"),
    "runtime_parity": ("receipt", "parity", "control-plane", "1682", "ruleset", "protected"),
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _extract_concepts(text: str) -> list[str]:
    lower = text.lower()
    matched: list[str] = []
    for concept, kws in _CONCEPT_KEYWORDS.items():
        if any(kw in lower for kw in kws):
            matched.append(concept)
    return matched


def _rel_ref(data_root: Path, path: Path, anchor: str = "") -> str:
    try:
        rel = path.resolve().relative_to(data_root.resolve()).as_posix()
    except ValueError:
        rel = str(path)
    return f"{rel}#{anchor}" if anchor else rel


def rebuild_relation_index(data_root: Path) -> dict[str, Any]:
    """Rebuild the evolvable relation graph strictly from read-only raw data."""
    root = Path(data_root).resolve()
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []

    def _add_node(node_id: str, kind: str, title: str, raw_ref: str, summary: str = "") -> None:
        if node_id not in nodes:
            nodes[node_id] = {
                "id": node_id,
                "kind": kind,
                "title": title,
                "raw_ref": raw_ref,
                "summary": summary[:280],
            }

    def _add_edge(src: str, dst: str, relation: str, raw_ref: str) -> None:
        edges.append({"source": src, "target": dst, "relation": relation, "raw_ref": raw_ref})

    # 1. Index projects/*/STATUS.md (read-only)
    projects_dir = root / "projects"
    if projects_dir.is_dir():
        for status_file in sorted(projects_dir.glob("*/STATUS.md")):
            project_name = status_file.parent.name
            try:
                content = status_file.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            ref = _rel_ref(root, status_file)
            proj_id = f"project:{project_name}"
            first_line = next((ln.strip("# ").strip() for ln in content.splitlines() if ln.strip()), project_name)
            _add_node(proj_id, "project", first_line, ref, summary=first_line)
            for concept in _extract_concepts(content):
                cid = f"concept:{concept}"
                _add_node(cid, "concept", concept, ref)
                _add_edge(proj_id, cid, "touches_concept", ref)

    # 2. Index personas/*/pitfalls_guardrails.md (read-only)
    personas_dir = root / "personas"
    if personas_dir.is_dir():
        for guard_file in sorted(personas_dir.glob("*/pitfalls_guardrails.md")):
            persona_name = guard_file.parent.name
            try:
                lines = guard_file.read_text(encoding="utf-8", errors="ignore").splitlines()
            except OSError:
                continue
            current_title = ""
            current_line = 1
            current_buf: list[str] = []

            def _flush_guardrail(title: str, line_no: int, body_lines: list[str]) -> None:
                if not title:
                    return
                body = " ".join(x.strip() for x in body_lines if x.strip())
                gid = f"guardrail:{persona_name}:L{line_no}"
                ref = _rel_ref(root, guard_file, f"L{line_no}")
                _add_node(gid, "guardrail", title, ref, summary=body)
                for concept in _extract_concepts(title + " " + body):
                    cid = f"concept:{concept}"
                    _add_node(cid, "concept", concept, ref)
                    _add_edge(gid, cid, "guards_concept", ref)

            for idx, line in enumerate(lines, start=1):
                if line.startswith("### "):
                    _flush_guardrail(current_title, current_line, current_buf)
                    current_title = line[4:].strip()
                    current_line = idx
                    current_buf = []
                elif current_title:
                    current_buf.append(line)
            _flush_guardrail(current_title, current_line, current_buf)

        # 3. Index personas/*/consolidated_experiences.jsonl (read-only)
        for exp_file in sorted(personas_dir.glob("*/consolidated_experiences.jsonl")):
            persona_name = exp_file.parent.name
            try:
                lines = exp_file.read_text(encoding="utf-8", errors="ignore").splitlines()
            except OSError:
                continue
            for idx, raw_line in enumerate(lines, start=1):
                raw_line = raw_line.strip()
                if not raw_line:
                    continue
                try:
                    rec = json.loads(raw_line)
                except ValueError:
                    continue
                card_id = str(rec.get("card_id") or f"L{idx}")
                title = str(rec.get("title") or card_id)
                summary = str(rec.get("summary") or "")
                eid = f"experience:{persona_name}:{card_id}"
                ref = _rel_ref(root, exp_file, f"L{idx}")
                _add_node(eid, "experience", title, ref, summary=summary)
                for concept in _extract_concepts(title + " " + summary):
                    cid = f"concept:{concept}"
                    _add_node(cid, "concept", concept, ref)
                    _add_edge(eid, cid, "evidences_concept", ref)

    graph = {
        "schema": GRAPH_SCHEMA,
        "indexer_version": INDEXER_VERSION,
        "rebuilt_at": _utc_now_iso(),
        "data_root_policy": "raw_data_immutable_index_rebuildable",
        "stats": {
            "node_count": len(nodes),
            "edge_count": len(edges),
        },
        "nodes": list(nodes.values()),
        "edges": edges,
    }

    out_dir = root / "knowledge"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "relation_graph.json"
    tmp = out_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(graph, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(out_path)
    return graph


def load_or_build_index(data_root: Path) -> dict[str, Any]:
    out_path = Path(data_root).resolve() / "knowledge" / "relation_graph.json"
    if out_path.is_file():
        try:
            data = json.loads(out_path.read_text(encoding="utf-8"))
            if data.get("schema") == GRAPH_SCHEMA:
                return data
        except (OSError, ValueError):
            pass
    return rebuild_relation_index(data_root)


def recall_for_task(
    data_root: Path,
    *,
    project: str,
    query_text: str,
    max_results: int = 5,
) -> list[dict[str, Any]]:
    """Recall-before-Act: retrieve relevant guardrails, experiences, and related projects with raw_ref."""
    graph = load_or_build_index(data_root)
    nodes_by_id = {n["id"]: n for n in graph.get("nodes") or []}
    query_concepts = set(_extract_concepts(f"{project} {query_text}"))
    query_tokens = {
        tok for tok in re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]{2,}", f"{project} {query_text}".lower())
        if len(tok) >= 2
    }

    # Collect nodes linked to matching concepts.
    concept_scores: dict[str, int] = {}
    for edge in graph.get("edges") or []:
        tgt = edge.get("target", "")
        src = edge.get("source", "")
        if tgt.startswith("concept:") and tgt.split(":", 1)[1] in query_concepts:
            concept_scores[src] = concept_scores.get(src, 0) + 3

    scored: list[tuple[int, dict[str, Any]]] = []
    for node_id, node in nodes_by_id.items():
        if node.get("kind") == "concept":
            continue
        if node_id == f"project:{project}":
            continue
        score = concept_scores.get(node_id, 0)
        haystack = f"{node.get('title', '')} {node.get('summary', '')}".lower()
        for tok in query_tokens:
            if tok in haystack:
                score += 1
        # Boost guardrails so past lessons surface first.
        if score > 0 and node.get("kind") == "guardrail":
            score += 2
        if score > 0:
            scored.append((score, node))

    scored.sort(key=lambda item: (-item[0], item[1]["id"]))
    return [
        {
            "id": n["id"],
            "kind": n["kind"],
            "title": n["title"],
            "summary": n.get("summary", ""),
            "raw_ref": n["raw_ref"],
            "score": s,
        }
        for s, n in scored[:max_results]
    ]
