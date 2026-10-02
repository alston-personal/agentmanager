import json

from agentos_node import executor_reconcile


def test_discovery_distinguishes_ready_discovered_and_unavailable(monkeypatch):
    binaries = {
        "claude": "C:/tools/claude.exe",
        "codex": "C:/tools/codex.exe",
        "gemini": None,
        "antigravity": None,
    }

    def fake_find(candidates):
        return binaries.get(candidates[0])

    def fake_bridge(provider):
        if provider == "claude-code":
            return {
                "bridge_ready": True,
                "bridge_capabilities": ["agent.session.inspect"],
            }
        return {
            "bridge_ready": False,
            "bridge_capabilities": [],
        }

    monkeypatch.setattr(executor_reconcile, "_find_binary", fake_find)
    monkeypatch.setattr(executor_reconcile, "_bridge_state", fake_bridge)
    monkeypatch.setattr(
        executor_reconcile,
        "_probe_version",
        lambda path: {"version_probe_ok": True, "version": "test-version"},
    )

    inventory = executor_reconcile.discover_executor_inventory()
    states = {item["executor_id"]: item for item in inventory["executors"]}

    assert states["claude-code"]["state"] == "READY"
    assert states["claude-code"]["routable"] is True
    assert states["codex"]["state"] == "DISCOVERED"
    assert states["codex"]["routable"] is False
    assert states["gemini"]["state"] == "UNAVAILABLE"


def test_reconcile_persists_adoption_state_atomically(tmp_path, monkeypatch):
    monkeypatch.setattr(
        executor_reconcile,
        "discover_executor_inventory",
        lambda: {
            "schema": executor_reconcile.SCHEMA,
            "executors": [
                {
                    "executor_id": "claude-code",
                    "state": "READY",
                    "adoptable": True,
                    "routable": True,
                    "bridge_capabilities": ["agent.session.inspect"],
                    "version": "1.0",
                },
                {
                    "executor_id": "codex",
                    "state": "DISCOVERED",
                    "adoptable": True,
                    "routable": False,
                    "bridge_capabilities": [],
                    "version": "2.0",
                },
                {
                    "executor_id": "gemini",
                    "state": "UNAVAILABLE",
                    "adoptable": False,
                    "routable": False,
                    "bridge_capabilities": [],
                    "version": None,
                },
            ],
        },
    )

    result = executor_reconcile.reconcile_executor_adoption(state_root=tmp_path)
    assert result["ok"] is True

    persisted = json.loads((tmp_path / "executor-adoption.json").read_text(encoding="utf-8"))
    assert persisted["schema"] == executor_reconcile.ADOPTION_SCHEMA
    assert persisted["summary"] == {
        "ready": 1,
        "discovered": 1,
        "unavailable": 1,
    }
