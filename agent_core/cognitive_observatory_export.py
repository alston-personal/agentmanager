"""Read-only export helpers for Cognitive Observatory timelines.

Exports are presentation artifacts only. They never mutate cognition or create
new authority. DOT output intentionally uses only stable snapshot/delta lineage
and metric summaries so visualization cannot be confused with a knowledge graph
truth store.
"""

from __future__ import annotations

import json
from typing import Any, Iterable


def export_timeline_json(
    timeline: Iterable[dict[str, Any]],
    deltas: Iterable[dict[str, Any]],
) -> str:
    payload = {
        "schema_version": "agentos.cognitive-observatory-export/v1",
        "timeline": list(timeline),
        "deltas": list(deltas),
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)


def _escape(value: object) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def export_timeline_dot(
    timeline: Iterable[dict[str, Any]],
    deltas: Iterable[dict[str, Any]],
    *,
    title: str = "AgentOS Cognitive Evolution",
) -> str:
    snapshots = list(timeline)
    delta_items = list(deltas)
    snapshot_ids = {item["snapshot_id"] for item in snapshots}

    lines = [
        "digraph cognition_timeline {",
        '  rankdir="LR";',
        f'  label="{_escape(title)}";',
        '  labelloc="t";',
        '  node [shape="box"];',
    ]

    for item in snapshots:
        payload = item.get("payload", {})
        metrics = payload.get("metrics", {})
        label_parts = [
            item.get("captured_at", ""),
            item.get("trigger_ref", ""),
            f"knowledge={metrics.get('knowledge_count', 0)}",
            f"relations={metrics.get('relation_count', 0)}",
            f"contradictions={metrics.get('contradiction_count', 0)}",
            f"archive={metrics.get('archive_memory_count', 0)}",
        ]
        label = "\\n".join(_escape(part) for part in label_parts if str(part))
        lines.append(f'  "{_escape(item["snapshot_id"])}" [label="{label}"];')

    for item in delta_items:
        source = item["from_snapshot_id"]
        target = item["to_snapshot_id"]
        if source not in snapshot_ids or target not in snapshot_ids:
            raise ValueError("delta export contains unknown snapshot lineage")
        payload = item.get("payload", {})
        metric_delta = payload.get("metric_delta", {})
        annotations = payload.get("annotations", [])
        edge_parts = []
        if annotations:
            edge_parts.append(", ".join(str(value) for value in annotations))
        if metric_delta:
            edge_parts.extend(
                f"{name}:{value:+d}" if isinstance(value, int) else f"{name}:{value}"
                for name, value in sorted(metric_delta.items())
            )
        edge_label = "\\n".join(_escape(part) for part in edge_parts)
        suffix = f' [label="{edge_label}"]' if edge_label else ""
        lines.append(f'  "{_escape(source)}" -> "{_escape(target)}"{suffix};')

    lines.append("}")
    return "\n".join(lines) + "\n"
