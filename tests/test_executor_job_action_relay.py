from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_core.executor_job_contract import canonical_experience_regression_request
from agentos_node import action_relay
from agentos_node.action_relay import ActionRelayWorker
from agentos_node.executor_job_action_relay import ACTION, ActionRelayExecutorJobDispatcher


@pytest.fixture(autouse=True)
def _no_system_group_mutation(monkeypatch):
    monkeypatch.setattr(action_relay, "_share", lambda *args, **kwargs: None)


def test_submit_uses_existing_action_relay_capsule_and_same_job_id(tmp_path: Path) -> None:
    dispatcher = ActionRelayExecutorJobDispatcher(tmp_path / "relay")
    submission = dispatcher.submit(node_id="oracle-core-node", request=canonical_experience_regression_request())
    job_id = submission["job_id"]

    capsule_path = tmp_path / "relay" / "inbox" / f"{job_id}.json"
    capsule = json.loads(capsule_path.read_text(encoding="utf-8"))
    assert capsule["action"] == ACTION
    assert capsule["capsule_id"] == job_id
    assert capsule["authority"]["arbitrary_shell"] is False
    assert set(capsule["params"]) == {"request"}
    assert "command" not in json.dumps(capsule).casefold()


def test_worker_terminal_receipt_projects_missing_provider_without_shell_fallback(tmp_path: Path) -> None:
    root = tmp_path / "relay"
    dispatcher = ActionRelayExecutorJobDispatcher(root)
    submission = dispatcher.submit(node_id="oracle-core-node", request=canonical_experience_regression_request())

    raw = ActionRelayWorker(root).process_one()
    assert raw is not None
    assert raw["schema"] == "agentos.action-receipt/v1"
    assert raw["action"] == ACTION
    assert raw["executor_available"] is False
    assert raw["classification"] == "JOB_IMPLEMENTATION_UNAVAILABLE"

    receipt = dispatcher.inspect(submission["job_id"])
    assert receipt is not None
    assert receipt["job_id"] == submission["job_id"]
    assert receipt["executor_available"] is False
    assert receipt["routable"] is False
    assert receipt["authorized"] is False
    assert receipt["successful"] is False
    assert receipt["classification"] == "JOB_IMPLEMENTATION_UNAVAILABLE"
    assert receipt["credential_exposed"] is False


def test_terminal_receipt_reconstructs_job_provenance_after_dispatcher_restart(tmp_path: Path) -> None:
    root = tmp_path / "relay"
    first = ActionRelayExecutorJobDispatcher(root)
    submission = first.submit(node_id="oracle-core-node", request=canonical_experience_regression_request())
    job_id = submission["job_id"]
    ActionRelayWorker(root).process_one()

    # A fresh controller/dispatcher has no in-memory request cache. It must be
    # able to recover only the fixed semantic identity persisted in the receipt.
    restarted = ActionRelayExecutorJobDispatcher(root)
    receipt = restarted.inspect(job_id)
    assert receipt is not None
    assert receipt["job_id"] == job_id
    assert receipt["job_type"] == "experience.regression"
    assert receipt["project_id"] == "agentos-core"
    assert receipt["executor_class"] == "openai-codex-local"
    assert receipt["classification"] == "JOB_IMPLEMENTATION_UNAVAILABLE"

    persisted = json.loads((root / "receipts" / f"{job_id}.json").read_text(encoding="utf-8"))
    assert persisted["schema"] == "agentos.action-receipt/v1"
    assert persisted["action"] == ACTION
    assert persisted["job_type"] == "experience.regression"
    assert "request" not in persisted
    assert "prompt" not in persisted
    assert "stdout" not in persisted
    assert "credential" not in persisted


def test_interrupted_processing_is_unknown_and_never_replayed(tmp_path: Path) -> None:
    root = tmp_path / "relay"
    dispatcher = ActionRelayExecutorJobDispatcher(root)
    submission = dispatcher.submit(node_id="oracle-core-node", request=canonical_experience_regression_request())
    job_id = submission["job_id"]

    source = root / "inbox" / f"{job_id}.json"
    processing = root / "processing" / source.name
    processing.parent.mkdir(parents=True, exist_ok=True)
    source.replace(processing)

    recovered = ActionRelayWorker(root).recover_interrupted()
    assert recovered == [job_id]
    assert not (root / "inbox" / f"{job_id}.json").exists()
    assert (root / "quarantine" / f"{job_id}.json").exists()

    receipt = dispatcher.inspect(job_id)
    assert receipt is not None
    assert receipt["successful"] is False
    assert receipt["classification"] == "EXECUTION_OUTCOME_UNKNOWN"


def test_forbidden_generic_execution_fields_are_rejected_before_spool(tmp_path: Path) -> None:
    dispatcher = ActionRelayExecutorJobDispatcher(tmp_path / "relay")
    request = canonical_experience_regression_request()
    request["command"] = "whoami"
    with pytest.raises(ValueError, match="forbidden generic-execution field"):
        dispatcher.submit(node_id="oracle-core-node", request=request)
    assert not (tmp_path / "relay" / "inbox").exists()
