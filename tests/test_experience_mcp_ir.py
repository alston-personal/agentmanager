from __future__ import annotations

import json

from agentos_node import experience_mcp_stdio as mcp


def test_hydration_receipt_records_manifest_without_ir_body(tmp_path, monkeypatch):
    receipt = tmp_path / "receipt.json"
    monkeypatch.setenv("AGENTOS_EXPERIENCE_HYDRATION_RECEIPT", str(receipt))
    monkeypatch.setenv("AGENTOS_RUNTIME_SOURCE_COMMIT", "test-sha")
    projection = {
        "source": "ONE_EXPERIENCE",
        "project_id": "agentos-core",
        "digest": "sha256:projection",
        "experience_ids": ["x.v1"],
        "items": [{
            "experience_id": "x.v1",
            "semantic_digest": "sha256:item",
            "expected_behavior_dimensions": ["governance"],
            "ir": {"schema": "agentos.experience-ir/v1", "nodes": [{"secret-free": True}]},
        }],
    }
    mcp._write_receipt(projection)
    stored = json.loads(receipt.read_text(encoding="utf-8"))
    assert stored["schema"] == "agentos.experience-hydration-receipt/v2"
    assert stored["semantic_manifest"] == [{
        "experience_id": "x.v1",
        "semantic_digest": "sha256:item",
        "expected_behavior_dimensions": ["governance"],
    }]
    assert "ir" not in stored["semantic_manifest"][0]
    assert stored["credential_exposed"] is False
