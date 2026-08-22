import json
from pathlib import Path


def test_execution_handoff_schema_requires_portable_operating_state():
    schema = json.loads(Path("contracts/execution-handoff-v1.schema.json").read_text())
    assert schema["$id"] == "agentos.execution-handoff/v1"
    required = set(schema["required"])
    assert {"goal", "execution_world", "disposition", "governance", "failure_knowledge", "checkpoint"} <= required


def test_live_reconciliation_is_mandatory():
    schema = json.loads(Path("contracts/execution-handoff-v1.schema.json").read_text())
    execution_world = schema["properties"]["execution_world"]
    assert "mutable_facts_require_live_reconciliation" in execution_world["required"]
    assert execution_world["properties"]["mutable_facts_require_live_reconciliation"]["const"] is True


def test_disposition_contract_is_explicit():
    schema = json.loads(Path("contracts/execution-handoff-v1.schema.json").read_text())
    disposition = schema["properties"]["disposition"]
    assert disposition["properties"]["contract"]["const"] == "agentos.execution-disposition/v1"
    assert "CONTINUE" in disposition["properties"]["current"]["enum"]
    assert "REQUEST_AUTHORITY" in disposition["properties"]["current"]["enum"]
