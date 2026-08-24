import json
from pathlib import Path


def _schema():
    return json.loads(Path("contracts/workstream-v1.schema.json").read_text())


def test_workstream_has_goal_lineage_and_canonical_parent():
    schema = _schema()
    assert schema["$id"] == "agentos.workstream/v1"
    required = set(schema["required"])
    assert {"workstream_id", "goal", "canonical_parent", "ownership", "integration"} <= required


def test_workstream_status_supports_parallel_lifecycle():
    statuses = set(_schema()["properties"]["status"]["enum"])
    assert {"READY", "RUNNING", "WAITING", "BLOCKED", "INTEGRATION_READY", "DONE"} <= statuses


def test_effectful_ownership_has_fencing_identity():
    ownership = _schema()["properties"]["ownership"]
    assert {"executor_id", "lease_id", "fencing_token"} <= set(ownership["required"])


def test_integration_is_distinct_from_execution_completion():
    values = set(_schema()["properties"]["integration"]["properties"]["disposition"]["enum"])
    assert {"READY", "CONFLICT", "ACCEPTED", "REJECTED", "SUPERSEDED"} <= values
