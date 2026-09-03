from __future__ import annotations

import pytest

from agent_core.controller_api import ControllerService


class FakeFabric:
    def __init__(self):
        self.receipts = {
            "ctl-existing": {
                "schema": "agentos.node-receipt/v0.1",
                "task_id": "ctl-existing",
                "node_id": "node-a",
                "action": "agent.surface.inspect",
                "ok": True,
            }
        }

    def get_receipt(self, task_id):
        return self.receipts.get(task_id)


class FakeExecutorDispatcher:
    def __init__(self, receipt=None):
        self.receipt = receipt
        self.inspected = []

    def inspect(self, job_id):
        self.inspected.append(job_id)
        return self.receipt


def test_action_job_receipt_delegates_to_executor_store_not_realm_fabric():
    dispatcher = FakeExecutorDispatcher({
        "schema": "agentos.executor-job-receipt/v1",
        "job_id": "action-12345678",
        "job_type": "experience.regression",
        "project_id": "agentos-core",
        "executor_class": "openai-codex-local",
        "executor_available": False,
        "routable": False,
        "authorized": False,
        "successful": False,
        "credential_exposed": False,
        "classification": "JOB_IMPLEMENTATION_UNAVAILABLE",
    })
    controller = ControllerService(FakeFabric(), executor_job_dispatcher=dispatcher)

    receipt = controller.receipt("action-12345678")
    assert receipt["job_id"] == "action-12345678"
    assert receipt["classification"] == "JOB_IMPLEMENTATION_UNAVAILABLE"
    assert dispatcher.inspected == ["action-12345678"]


def test_pending_action_job_is_reported_as_not_found_for_existing_poll_contract():
    dispatcher = FakeExecutorDispatcher(None)
    controller = ControllerService(FakeFabric(), executor_job_dispatcher=dispatcher)
    with pytest.raises(KeyError):
        controller.receipt("action-12345678")
    assert dispatcher.inspected == ["action-12345678"]


def test_ordinary_node_receipt_stays_on_realm_fabric_path():
    dispatcher = FakeExecutorDispatcher({"unexpected": True})
    controller = ControllerService(FakeFabric(), executor_job_dispatcher=dispatcher)
    receipt = controller.receipt("ctl-existing")
    assert receipt["schema"] == "agentos.node-receipt/v0.1"
    assert receipt["task_id"] == "ctl-existing"
    assert dispatcher.inspected == []
