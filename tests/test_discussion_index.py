from pathlib import Path

import pytest

from agent_core.discussion_index import (
    append_record,
    read_records,
    search_from_one,
    search_records,
    validate_record,
)


def record(
    discussion_id: str = "discussion-1",
    *,
    surface: str = "chatgpt-web",
    node_id: str = "oracle-core-node",
    summary: str = "Discussed Master Experience Floor and ONE hydration regression.",
):
    return {
        "schema": "agentos.discussion-record/v1",
        "discussion_id": discussion_id,
        "project_id": "agentos-core",
        "realm_id": "default",
        "observed_start": "2026-09-01T00:00:00Z",
        "observed_end": "2026-09-01T00:10:00Z",
        "provenance": {
            "node_id": node_id,
            "surface": surface,
            "executor_adapter": f"{surface}-adapter",
            "backend_model": "unknown",
            "session_ref": f"session://{discussion_id}",
            "source_ref": f"provider://{surface}/{discussion_id}",
        },
        "semantic": {
            "summary": summary,
            "topics": ["Master Experience Floor", "ONE"],
            "entities": ["AgentOS"],
            "keywords": ["hydration", "regression"],
        },
        "refs": {
            "canonical_ir": ["ir://agentos-core/1"],
            "experience": ["experience://agentos-core/floor"],
            "issues": ["github://agentmanager/issues/117"],
            "receipts": [],
            "assignments": [],
        },
        "promoted_to": ["experience://agentos-core/floor"],
        "privacy": {"storage_class": "indexed_projection"},
    }


def test_record_keeps_node_surface_backend_session_distinct():
    value = validate_record(record())
    assert value["provenance"]["node_id"] == "oracle-core-node"
    assert value["provenance"]["surface"] == "chatgpt-web"
    assert value["provenance"]["backend_model"] == "unknown"
    assert value["provenance"]["session_ref"] == "session://discussion-1"
    assert value["promoted_to"] == ["experience://agentos-core/floor"]


def test_search_returns_provenance_and_canonical_links():
    unrelated = record(
        "discussion-2",
        surface="openai-codex",
        summary="Investigated unrelated runtime packaging details.",
    )
    unrelated["semantic"] = {
        "summary": "Investigated unrelated runtime packaging details.",
        "topics": ["runtime packaging"],
        "entities": ["Python"],
        "keywords": ["wheel"],
    }
    unrelated["promoted_to"] = []
    result = search_records([record(), unrelated], text="Master Experience Floor")
    assert result["read_only"] is True
    assert result["canonical_authority"] is False
    assert result["count"] == 1
    hit = result["results"][0]
    assert hit["discussion_id"] == "discussion-1"
    assert hit["provenance"]["surface"] == "chatgpt-web"
    assert hit["refs"]["issues"] == ["github://agentmanager/issues/117"]
    assert hit["promoted_to"] == ["experience://agentos-core/floor"]


def test_store_is_idempotent_and_conflicts_fail_closed(tmp_path: Path):
    first = append_record(record(), data_root=tmp_path)
    second = append_record(record(), data_root=tmp_path)
    assert first["persisted"] is True
    assert second["persisted"] is False
    assert len(read_records("agentos-core", data_root=tmp_path)) == 1

    changed = record(summary="A different semantic record under the same id.")
    with pytest.raises(ValueError, match="different semantic digest"):
        append_record(changed, data_root=tmp_path)


def test_secret_like_projection_is_rejected():
    value = record(summary="Use Authorization: Bearer abcdefghijklmnopqrstuvwxyz123456")
    with pytest.raises(ValueError, match="secret-like"):
        validate_record(value)


def test_cross_surface_search_and_filter(tmp_path: Path):
    append_record(record(), data_root=tmp_path)
    append_record(
        record(
            "discussion-2",
            surface="openai-codex",
            node_id="vopc5750",
            summary="Master Experience Floor comparison through Codex.",
        ),
        data_root=tmp_path,
    )

    all_hits = search_from_one(
        project_id="agentos-core",
        text="Master Experience Floor",
        data_root=tmp_path,
    )
    assert all_hits["count"] == 2

    codex = search_from_one(
        project_id="agentos-core",
        text="Master Experience Floor",
        surface="openai-codex",
        data_root=tmp_path,
    )
    assert codex["count"] == 1
    assert codex["results"][0]["provenance"]["node_id"] == "vopc5750"
