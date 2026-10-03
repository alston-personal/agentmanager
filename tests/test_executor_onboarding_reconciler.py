from __future__ import annotations

from unittest.mock import patch

from agent_core import executor_onboarding_reconciler as reconciler


def test_core_candidate_discovery_queues_registration_required_and_unmanaged_surface():
    node_map = {
        "nodes": [
            {
                "node_id": "vopc5750",
                "status": "online",
                "executor_inventory": {
                    "executors": [
                        {
                            "executor_id": "claude-code",
                            "state": "REGISTRATION_REQUIRED",
                        }
                    ]
                },
                "surface_inventory": {
                    "surfaces": [
                        {
                            "surface_id": "agent-runtime:claude-code",
                            "provider": "claude-code",
                            "kind": "agent-runtime",
                            "capabilities": ["agent.chat", "code.edit"],
                        },
                        {
                            "surface_id": "app:browser",
                            "provider": "browser",
                            "kind": "app",
                            "capabilities": [],
                        },
                    ]
                },
            }
        ]
    }

    with patch("agent_core.executor_onboarding_reconciler.NodeRegistry") as registry:
        registry.return_value.node_map.return_value = node_map
        rows = reconciler.discover_core_candidates()

    assert len(rows) == 2
    assert {row["reason"] for row in rows} == {
        "registration_required",
        "unmanaged_surface",
    }
    assert all(len(row["fingerprint"]) == 24 for row in rows)


def test_ready_executor_does_not_create_profile_candidate():
    node_map = {
        "nodes": [
            {
                "node_id": "node-a",
                "status": "online",
                "executor_inventory": {
                    "executors": [
                        {
                            "executor_id": "demo",
                            "state": "READY",
                        }
                    ]
                },
                "surface_inventory": {
                    "surfaces": [
                        {
                            "surface_id": "agent-runtime:demo",
                            "provider": "demo",
                            "kind": "agent-runtime",
                            "capabilities": ["agent.chat"],
                        }
                    ]
                },
            }
        ]
    }

    with patch("agent_core.executor_onboarding_reconciler.NodeRegistry") as registry:
        registry.return_value.node_map.return_value = node_map
        rows = reconciler.discover_core_candidates()

    assert rows == []
