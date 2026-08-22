import json
from pathlib import Path

from agent_core.relational_seed import load_relation_seed


def test_real_agentos_zeus_writer_shadow_seed_loads_and_resolves_alias():
    path = Path("config/relational-seeds/agentos-zeus-writer.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    loaded = load_relation_seed(payload)
    graph = loaded.build_graph()

    matches = graph.resolve("同源雙模小說")
    assert loaded.mode == "shadow"
    assert matches
    assert matches[0].entity_id == "project:zeus-writer"

    related = graph.related_entity_ids("同源雙模小說", max_depth=2)
    assert "work:ai-fantasy-chronicles" in related
    assert "artifact:agentos-grand-chronicle" in related


def test_seed_has_no_placeholder_hashes_and_validated_edges_are_grounded():
    payload = json.loads(
        Path("config/relational-seeds/agentos-zeus-writer.json").read_text(encoding="utf-8")
    )
    loaded = load_relation_seed(payload)
    for relation in loaded.relations:
        assert all("pending" not in item.content_hash.lower() for item in relation.evidence)
        if relation.status == "validated":
            assert relation.evidence


def test_seed_loader_rejects_non_shadow_mode():
    payload = {
        "schema_version": "agentos.relation-seed/v1",
        "mode": "production",
        "entities": [],
        "relations": [],
    }
    try:
        load_relation_seed(payload)
    except ValueError as exc:
        assert "shadow" in str(exc)
    else:
        raise AssertionError("non-shadow relation seed must fail closed")


def test_seed_loader_rejects_placeholder_evidence_hash():
    payload = {
        "schema_version": "agentos.relation-seed/v1",
        "mode": "shadow",
        "entities": [
            {"entity_id": "a", "kind": "project", "canonical_name": "A"},
            {"entity_id": "b", "kind": "project", "canonical_name": "B"}
        ],
        "relations": [
            {
                "subject_id": "a",
                "predicate": "related_to",
                "object_id": "b",
                "status": "candidate",
                "evidence": [
                    {
                        "source_kind": "github",
                        "source_ref": "x",
                        "content_hash": "pending_live_hash"
                    }
                ]
            }
        ]
    }
    try:
        load_relation_seed(payload)
    except ValueError as exc:
        assert "placeholder" in str(exc)
    else:
        raise AssertionError("placeholder evidence must fail closed")
