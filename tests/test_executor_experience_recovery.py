import json

from agentos_node.executor_experience_recovery import enqueue_executor_experience_harvest, plan_executor_experience_recovery


def test_only_running_executor_with_declared_harvest_bridge_is_eligible():
    result = plan_executor_experience_recovery({"node_id": "node-1", "surface_inventory": {"surfaces": [
        {"provider": "gemini", "surface_id": "agent-runtime:gemini", "running": True, "capabilities": ["agent.chat", "agent.context.harvest"]},
        {"provider": "codex", "surface_id": "agent-runtime:codex", "running": True, "capabilities": ["agent.chat"]},
        {"provider": "claude-code", "surface_id": "agent-runtime:claude-code", "running": False, "capabilities": ["agent.context.harvest"]},
    ]}})
    assert result["eligible_providers"] == ["gemini"]
    assert result["experience_promoted"] == 0
    assert result["raw_conversation_scraped"] is False


def test_process_presence_does_not_grant_history_access():
    result = plan_executor_experience_recovery({"node_id": "node-1", "surface_inventory": {"surfaces": [
        {"provider": "gemini", "surface_id": "agent-runtime:gemini", "running": True, "capabilities": ["agent.chat"]},
    ]}})
    assert result["eligible_providers"] == []
    assert result["executors"][0]["reason"] == "no_declared_harvest_bridge"


def test_eligible_gemini_queues_summary_only_historical_ir_harvest(monkeypatch, tmp_path):
    bridge = tmp_path / "gemini"
    bridge.mkdir()
    (bridge / "bridge.json").write_text(json.dumps({
        "schema": "agentos.session-bridge/v0.1", "provider": "gemini", "ready": True,
        "operations": ["harvest"],
    }), encoding="utf-8")
    monkeypatch.setenv("AGENTOS_GEMINI_BRIDGE", str(bridge))
    report = enqueue_executor_experience_harvest({"node_id": "node-1", "surface_inventory": {"surfaces": [
        {"provider": "gemini", "surface_id": "agent-runtime:gemini", "running": True, "capabilities": ["agent.context.harvest"]},
    ]}})
    assert report["harvest_requests_enqueued"] == 1
    request = json.loads(next((bridge / "requests").glob("*.json")).read_text(encoding="utf-8"))
    assert request["operation"] == "harvest"
    assert request["payload"]["output_schema"] == "agentos.historical-ir/v1"
    assert request["payload"]["raw_conversation_allowed"] is False
