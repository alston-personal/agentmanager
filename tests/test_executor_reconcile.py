import json
from pathlib import Path

from agentos_node import executor_reconcile
from agentos_node import executor_provider_registry


class ReadyProvider:
    executor_id = "demo"
    provider_id = "demo-provider"
    executor_class = "demo-class"

    def capabilities(self):
        return ["agent.chat"]

    def discover(self):
        return {"installed": True}

    def health(self):
        return {
            "reachable": True,
            "authorized": True,
            "routable": True,
            "healthy": True,
            "classification": "READY",
        }

    def invoke(self, request):
        return {"ok": True}

    def cancel(self, invocation_id):
        return {"ok": True}

    def receipt(self, invocation_id):
        return {"ok": True}


def _profile(adapter_module=None):
    return {
        "schema": "agentos.executor-provider-profile/v0.1",
        "executor_id": "demo",
        "provider_id": "demo-provider",
        "executor_class": "demo-class",
        "modes": ["cli"],
        "capabilities": ["agent.chat"],
        "discovery": {
            "strategy": ["provider_adapter"],
            "provider_owned_allowlists_only": True,
            "credential_access": False,
        },
        "readiness": {
            "dimensions": ["installed", "reachable", "authorized", "routable", "healthy"],
            "ready_requires": ["installed", "reachable", "authorized", "routable", "healthy"],
        },
        "invocation": {
            "bounded_semantic_requests_only": True,
            "caller_supplied_executable": False,
            "caller_supplied_argv": False,
            "caller_supplied_env": False,
        },
        "cancellation": {"supported": True, "strategy": "provider-defined"},
        "concurrency": {"model": "single", "mutex_scope": "demo"},
        "receipt": {"required": True, "secrets_allowed": False},
        "smoke": {"required": True, "kind": "bounded", "expected_safe_evidence": []},
        "adoption": {"reinstall_by_default": False, "preserve_existing_identity": True},
        "implementation": {
            "adapter_module": adapter_module,
            "notes": "test",
        },
    }


def test_profile_without_adapter_is_registration_required(tmp_path):
    root = tmp_path / "profiles"
    root.mkdir()
    (root / "demo.json").write_text(json.dumps(_profile()), encoding="utf-8")

    inventory = executor_reconcile.discover_executor_inventory(profile_root=root)
    assert inventory["schema"] == executor_reconcile.SCHEMA
    assert len(inventory["executors"]) == 1
    item = inventory["executors"][0]
    assert item["executor_id"] == "demo"
    assert item["state"] == "REGISTRATION_REQUIRED"
    assert item["routable"] is False


def test_registered_provider_can_be_ready(tmp_path, monkeypatch):
    root = tmp_path / "profiles"
    root.mkdir()
    (root / "demo.json").write_text(
        json.dumps(_profile("tests.fake_demo_provider")),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        executor_provider_registry,
        "_load_symbol",
        lambda spec: ReadyProvider(),
    )

    inventory = executor_reconcile.discover_executor_inventory(profile_root=root)
    item = inventory["executors"][0]
    assert item["state"] == "READY"
    assert item["routable"] is True
    assert item["authorized"] is True
    assert item["healthy"] is True


def test_reconcile_persists_state_counts(tmp_path, monkeypatch):
    monkeypatch.setattr(
        executor_reconcile,
        "discover_executor_inventory",
        lambda **kwargs: {
            "schema": executor_reconcile.SCHEMA,
            "provider_profile_schema": "agentos.executor-provider-profile/v0.1",
            "executors": [
                {
                    "executor_id": "ready",
                    "provider_id": "p1",
                    "executor_class": "c1",
                    "state": "READY",
                    "adoptable": True,
                    "routable": True,
                    "profile_valid": True,
                    "adapter_registered": True,
                    "discovered": True,
                    "authorized": True,
                    "healthy": True,
                    "capabilities": ["agent.chat"],
                },
                {
                    "executor_id": "missing-adapter",
                    "provider_id": "p2",
                    "executor_class": "c2",
                    "state": "REGISTRATION_REQUIRED",
                    "adoptable": False,
                    "routable": False,
                    "profile_valid": True,
                    "adapter_registered": False,
                    "discovered": False,
                    "authorized": False,
                    "healthy": False,
                    "capabilities": [],
                },
            ],
        },
    )

    result = executor_reconcile.reconcile_executor_adoption(state_root=tmp_path)
    assert result["ok"] is True

    persisted = json.loads((tmp_path / "executor-adoption.json").read_text(encoding="utf-8"))
    assert persisted["schema"] == executor_reconcile.ADOPTION_SCHEMA
    assert persisted["summary"] == {
        "total": 2,
        "ready": 1,
        "by_state": {
            "READY": 1,
            "REGISTRATION_REQUIRED": 1,
        },
    }


def test_fast_inventory_defers_provider_health(tmp_path, monkeypatch):
    root = tmp_path / "profiles"
    root.mkdir()
    (root / "demo.json").write_text(
        json.dumps(_profile("tests.fake_demo_provider")),
        encoding="utf-8",
    )

    provider = ReadyProvider()
    monkeypatch.setattr(executor_provider_registry, "_load_symbol", lambda spec: provider)
    monkeypatch.setattr(provider, "health", lambda: (_ for _ in ()).throw(AssertionError("health must be deferred")))

    inventory = executor_reconcile.discover_executor_inventory(
        profile_root=root,
        probe_health=False,
    )
    item = inventory["executors"][0]
    assert item["state"] == "DISCOVERED"
    assert item["health_deferred"] is True
    assert item["routable"] is False
    assert item["authorized"] is False
    assert item["healthy"] is False


def test_packaged_provider_profiles_match_repo_canonical_profiles():
    repo_root = Path(__file__).resolve().parents[1]
    packaged = repo_root / "agentos_node" / "executor_profiles"
    canonical = repo_root / ".agentos" / "executors"
    for name in ("antigravity.json", "claude-code.json", "codex.json", "gemini.json", "provider-profile.schema.json"):
        assert (packaged / name).read_text(encoding="utf-8") == (canonical / name).read_text(encoding="utf-8")


def test_reconcile_requires_two_ready_snapshots_before_stable_routing(tmp_path, monkeypatch):
    state = {"current": "READY"}

    def inventory(**kwargs):
        ready = state["current"] == "READY"
        return {
            "schema": executor_reconcile.SCHEMA,
            "provider_profile_schema": "agentos.executor-provider-profile/v0.1",
            "executors": [{
                "executor_id": "demo",
                "provider_id": "demo-provider",
                "executor_class": "demo-class",
                "state": state["current"],
                "adoptable": True,
                "routable": ready,
                "profile_valid": True,
                "adapter_registered": True,
                "discovered": True,
                "reachable": True,
                "authorized": ready,
                "healthy": ready,
                "provider_health": {"classification": "READY" if ready else "TIMEOUT"},
                "capabilities": ["agent.chat"],
            }],
        }

    monkeypatch.setattr(executor_reconcile, "discover_executor_inventory", inventory)

    first = executor_reconcile.reconcile_executor_adoption(state_root=tmp_path)["executor_adoption"]
    row1 = first["executors"][0]
    assert row1["ready_streak"] == 1
    assert row1["stable_routable"] is False
    assert first["observed_at"].endswith("Z")
    assert row1["provider_health"]["classification"] == "READY"

    second = executor_reconcile.reconcile_executor_adoption(state_root=tmp_path)["executor_adoption"]
    row2 = second["executors"][0]
    assert row2["ready_streak"] == 2
    assert row2["stable_routable"] is True

    state["current"] = "UNHEALTHY"
    third = executor_reconcile.reconcile_executor_adoption(state_root=tmp_path)["executor_adoption"]
    row3 = third["executors"][0]
    assert row3["ready_streak"] == 0
    assert row3["stable_routable"] is False
    assert row3["provider_health"]["classification"] == "TIMEOUT"


def test_reconcile_persists_provider_error_type_without_message(tmp_path, monkeypatch):
    monkeypatch.setattr(
        executor_reconcile,
        "discover_executor_inventory",
        lambda **kwargs: {
            "schema": executor_reconcile.SCHEMA,
            "provider_profile_schema": "agentos.executor-provider-profile/v0.1",
            "executors": [{
                "executor_id": "demo",
                "provider_id": "demo-provider",
                "executor_class": "demo-class",
                "state": "UNHEALTHY",
                "adoptable": True,
                "routable": False,
                "profile_valid": True,
                "adapter_registered": True,
                "discovered": True,
                "reachable": True,
                "authorized": False,
                "healthy": False,
                "provider_error": "RuntimeError",
                "capabilities": [],
            }],
        },
    )
    payload = executor_reconcile.reconcile_executor_adoption(state_root=tmp_path)["executor_adoption"]
    row = payload["executors"][0]
    assert row["provider_error"] == "RuntimeError"
    assert "secret" not in json.dumps(row)


class ExplodingProvider(ReadyProvider):
    def health(self):
        raise RuntimeError("private details must not persist")


class UnclassifiedUnhealthyProvider(ReadyProvider):
    def health(self):
        return {
            "reachable": True,
            "authorized": False,
            "routable": False,
            "healthy": False,
            "state": "UNHEALTHY",
        }


def test_health_exception_gets_bounded_provider_classification(tmp_path, monkeypatch):
    root = tmp_path / "profiles"
    root.mkdir()
    (root / "demo.json").write_text(
        json.dumps(_profile("tests.fake_demo_provider")),
        encoding="utf-8",
    )
    monkeypatch.setattr(executor_provider_registry, "_load_symbol", lambda spec: ExplodingProvider())
    item = executor_reconcile.discover_executor_inventory(profile_root=root)["executors"][0]
    assert item["state"] == "UNHEALTHY"
    assert item["provider_error"] == "RuntimeError"
    assert item["provider_health"]["classification"] == "PROVIDER_EXCEPTION_RUNTIMEERROR"
    assert "private details" not in json.dumps(item)


def test_nonready_health_without_classification_gets_safe_fallback(tmp_path, monkeypatch):
    root = tmp_path / "profiles"
    root.mkdir()
    (root / "demo.json").write_text(
        json.dumps(_profile("tests.fake_demo_provider")),
        encoding="utf-8",
    )
    monkeypatch.setattr(executor_provider_registry, "_load_symbol", lambda spec: UnclassifiedUnhealthyProvider())
    item = executor_reconcile.discover_executor_inventory(profile_root=root)["executors"][0]
    assert item["state"] == "UNHEALTHY"
    assert item["provider_health"]["classification"] == "UNCLASSIFIED_UNHEALTHY"
