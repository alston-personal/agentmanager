import json

from agentos_node import executor_onboarding


def test_surface_candidates_require_agent_semantics(tmp_path):
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    inventory = {
        "surfaces": [
            {
                "surface_id": "agent-runtime:new-ai",
                "provider": "new-ai",
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
    }
    candidates = executor_onboarding.classify_surface_candidates(
        node_id="node-a",
        surface_inventory=inventory,
        profile_root=profiles,
    )
    assert [item["provider_hint"] for item in candidates] == ["new-ai"]
    assert candidates[0]["needs_profile"] is True


def test_onboarding_plan_deduplicates_active_candidate(tmp_path):
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    inventory = {
        "surfaces": [
            {
                "surface_id": "agent-runtime:new-ai",
                "provider": "new-ai",
                "kind": "agent-runtime",
                "capabilities": ["agent.chat"],
            }
        ]
    }
    adoption = {"executors": []}
    first = executor_onboarding.plan_executor_onboarding(
        node_id="node-a",
        surface_inventory=inventory,
        adoption=adoption,
        state_root=tmp_path,
        profile_root=profiles,
    )
    second = executor_onboarding.plan_executor_onboarding(
        node_id="node-a",
        surface_inventory=inventory,
        adoption=adoption,
        state_root=tmp_path,
        profile_root=profiles,
    )
    assert first["queued_count"] == 1
    assert second["queued_count"] == 0
    assert second["active_count"] == 1
    intent = next(iter(second["intents"].values()))
    assert intent["state"] == "ONBOARDING_QUEUED"
    assert intent["attempt"] == 1
    assert intent["required_outputs"] == [
        "provider_profile",
        "provider_adapter",
        "provider_tests",
        "smoke_test",
        "receipt_contract",
    ]
