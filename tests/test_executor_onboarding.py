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


def test_registered_unhealthy_provider_is_not_requeued_for_code_integration(tmp_path):
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    (profiles / "demo.json").write_text(json.dumps({
        "schema": "agentos.executor-provider-profile/v0.1",
        "executor_id": "demo",
        "provider_id": "demo-provider",
        "executor_class": "demo-class",
        "modes": ["cli"],
        "capabilities": ["agent.chat"],
        "discovery": {"strategy": ["provider_adapter"], "provider_owned_allowlists_only": True, "credential_access": False},
        "readiness": {"dimensions": ["installed","reachable","authorized","routable","healthy"], "ready_requires": ["installed","reachable","authorized","routable","healthy"]},
        "invocation": {"bounded_semantic_requests_only": True, "caller_supplied_executable": False, "caller_supplied_argv": False, "caller_supplied_env": False},
        "cancellation": {"supported": False, "strategy": "provider-defined"},
        "concurrency": {"model": "single", "mutex_scope": "demo"},
        "receipt": {"required": True, "secrets_allowed": False},
        "smoke": {"required": True, "kind": "bounded", "expected_safe_evidence": []},
        "adoption": {"reinstall_by_default": False, "preserve_existing_identity": True},
        "implementation": {"adapter_module": "tests.fake_demo_provider", "notes": "test"}
    }), encoding="utf-8")
    inventory = {
        "surfaces": [{
            "surface_id": "agent-runtime:demo",
            "provider": "demo-provider",
            "kind": "agent-runtime",
            "capabilities": ["agent.chat"],
        }]
    }
    adoption = {
        "executors": [{
            "executor_id": "demo",
            "provider_id": "demo-provider",
            "state": "UNHEALTHY",
            "adapter_registered": True,
        }]
    }
    plan = executor_onboarding.plan_executor_onboarding(
        node_id="node-a",
        surface_inventory=inventory,
        adoption=adoption,
        state_root=tmp_path / "state",
        profile_root=profiles,
    )
    assert plan["queued_count"] == 0
    assert plan["active_count"] == 0
