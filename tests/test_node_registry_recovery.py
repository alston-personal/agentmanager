from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_core.node_registry import NodeRegistry


def snapshot(*, realm_id: str = "realm-alston", heartbeat: str = "2026-09-09T00:00:00Z") -> dict:
    return {
        "schema": "agentos.node-registry/v0.1",
        "realm_id": realm_id,
        "nodes": {
            "oracle-employee-wake-node": {
                "node_id": "oracle-employee-wake-node",
                "role": "client",
                "hostname": "oracle",
                "platform": "linux",
                "platform_release": "test",
                "capabilities": ["agent.employee.wake.deliver"],
                "tool_presence": {},
                "surface_inventory": {},
                "runtime": {},
                "workspace_roots": {},
                "status": "online",
                "first_seen_at": "2026-09-09T00:00:00Z",
                "last_manifest_at": "2026-09-09T00:00:00Z",
                "last_heartbeat_at": heartbeat,
                "benchmark": None,
            }
        },
    }


def heartbeat(*, observed_at: str = "2026-09-09T00:02:00Z") -> dict:
    return {
        "schema": "agentos.node-heartbeat/v0.1",
        "realm_id": "realm-alston",
        "node_id": "oracle-employee-wake-node",
        "status": "online",
        "observed_at": observed_at,
        "uptime_seconds": 10,
        "surface_count": 0,
    }


def test_normal_single_registry_json_loads_unchanged(tmp_path: Path):
    path = tmp_path / "nodes.json"
    expected = snapshot()
    path.write_text(json.dumps(expected), encoding="utf-8")
    assert NodeRegistry(path).load() == expected


def test_complete_same_realm_concatenated_snapshots_recover_latest(tmp_path: Path):
    path = tmp_path / "nodes.json"
    first = snapshot(heartbeat="2026-09-09T00:00:00Z")
    second = snapshot(heartbeat="2026-09-09T00:01:00Z")
    path.write_text(json.dumps(first) + "\n" + json.dumps(second) + "\n", encoding="utf-8")
    loaded = NodeRegistry(path).load()
    assert loaded == second


def test_mutation_after_recovery_canonicalizes_to_one_json_document(tmp_path: Path):
    path = tmp_path / "nodes.json"
    first = snapshot(heartbeat="2026-09-09T00:00:00Z")
    second = snapshot(heartbeat="2026-09-09T00:01:00Z")
    path.write_text(json.dumps(first) + "\n" + json.dumps(second) + "\n", encoding="utf-8")
    registry = NodeRegistry(path)
    registry.record_heartbeat(heartbeat())

    text = path.read_text(encoding="utf-8")
    decoded = json.loads(text)
    assert decoded["nodes"]["oracle-employee-wake-node"]["last_heartbeat_at"] == "2026-09-09T00:02:00Z"
    decoder = json.JSONDecoder()
    _, end = decoder.raw_decode(text)
    assert text[end:].strip() == ""


def test_concatenated_snapshots_from_different_realms_fail_closed(tmp_path: Path):
    path = tmp_path / "nodes.json"
    path.write_text(
        json.dumps(snapshot(realm_id="realm-alston")) + "\n" + json.dumps(snapshot(realm_id="realm-other")),
        encoding="utf-8",
    )
    with pytest.raises(json.JSONDecodeError):
        NodeRegistry(path).load()


@pytest.mark.parametrize(
    "suffix",
    [
        '{"schema":',
        "garbage",
        "[]",
    ],
)
def test_truncated_garbage_or_non_object_tail_fails_closed(tmp_path: Path, suffix: str):
    path = tmp_path / "nodes.json"
    path.write_text(json.dumps(snapshot()) + "\n" + suffix, encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        NodeRegistry(path).load()
