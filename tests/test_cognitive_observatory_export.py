import json

from agent_core.cognitive_observatory_export import export_timeline_dot, export_timeline_json


def timeline():
    return (
        {
            "snapshot_id": "snap_a",
            "captured_at": "2026-08-21T00:00:00Z",
            "trigger_ref": "review:a",
            "payload": {
                "metrics": {
                    "knowledge_count": 2,
                    "relation_count": 1,
                    "contradiction_count": 0,
                    "archive_memory_count": 0,
                }
            },
            "recorded_at": "2026-08-21T00:00:01Z",
        },
        {
            "snapshot_id": "snap_b",
            "captured_at": "2026-08-22T00:00:00Z",
            "trigger_ref": "review:b",
            "payload": {
                "metrics": {
                    "knowledge_count": 3,
                    "relation_count": 2,
                    "contradiction_count": 1,
                    "archive_memory_count": 1,
                }
            },
            "recorded_at": "2026-08-22T00:00:01Z",
        },
    )


def deltas():
    return (
        {
            "delta_id": "delta_ab",
            "from_snapshot_id": "snap_a",
            "to_snapshot_id": "snap_b",
            "payload": {
                "metric_delta": {"knowledge_count": 1, "relation_count": 1},
                "annotations": ["global_rereview"],
            },
            "recorded_at": "2026-08-22T00:00:02Z",
        },
    )


def test_json_export_preserves_timeline_and_delta_evidence():
    payload = json.loads(export_timeline_json(timeline(), deltas()))
    assert payload["schema_version"] == "agentos.cognitive-observatory-export/v1"
    assert [item["snapshot_id"] for item in payload["timeline"]] == ["snap_a", "snap_b"]
    assert payload["deltas"][0]["delta_id"] == "delta_ab"


def test_dot_export_visualizes_only_snapshot_lineage_and_metrics():
    dot = export_timeline_dot(timeline(), deltas(), title='Cognition "Review"')
    assert 'digraph cognition_timeline' in dot
    assert 'Cognition \\"Review\\"' in dot
    assert 'knowledge=2' in dot
    assert 'contradictions=1' in dot
    assert '"snap_a" -> "snap_b"' in dot
    assert 'global_rereview' in dot
    assert 'knowledge_count:+1' in dot


def test_dot_export_rejects_dangling_delta_lineage():
    broken = ({
        "delta_id": "bad",
        "from_snapshot_id": "snap_a",
        "to_snapshot_id": "missing",
        "payload": {},
        "recorded_at": "t",
    },)
    try:
        export_timeline_dot(timeline(), broken)
    except ValueError as exc:
        assert "unknown snapshot lineage" in str(exc)
    else:
        raise AssertionError("dangling observatory lineage must fail closed")
