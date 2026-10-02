from pathlib import Path

import pytest

from agent_core.runner_window import catalog, public_intent_for_action, resolve_intent
from agentos_node import bootstrap_control as bc


def test_runner_window_hides_runner_identity_from_submit_contract():
    intent, params = resolve_intent(
        "browser.gui",
        "smoke",
        source_commit="a" * 40,
        payload={},
    )
    assert intent.action == bc.ACTION_SMOKE_GUI_WORKER
    assert params == {"source_commit": "a" * 40}
    public = public_intent_for_action(intent.action)
    assert public == {"capability": "browser.gui", "operation": "smoke"}


def test_runner_window_rejects_unknown_intent():
    with pytest.raises(ValueError):
        resolve_intent("future.unknown", "run", source_commit="a" * 40, payload={})


def test_runner_window_rejects_unregistered_payload_keys():
    with pytest.raises(ValueError):
        resolve_intent("browser.gui", "smoke", source_commit="a" * 40, payload={"runner": "oracle-gui"})


def test_runner_window_catalog_contains_stable_public_intents():
    items = {(x["capability"], x["operation"]) for x in catalog()}
    assert ("agentos.dispatch", "probe") in items
    assert ("browser.gui", "smoke") in items
    assert ("social.runtime", "deploy") in items
    assert ("social.publish", "mio.approved") in items
    assert ("persona.runtime", "oursong.activate") in items


def test_gateway_exposes_runner_window_without_exposing_legacy_dispatch():
    route = Path("dashboard/app/api/agentos/[...path]/route.ts").read_text(encoding="utf-8")
    assert '"/v1/dispatch"' in route
    assert "v1\\/dispatch\\/requests" in route
    assert '"/v1/controller/dispatch"' not in route


def test_normal_workflows_use_runner_window_client():
    for path in (
        Path(".github/workflows/runner-pool-https-live-acceptance.yml"),
        Path(".github/workflows/oracle-social-runtime-rollout.yml"),
        Path(".github/workflows/oracle-publish-mio-approved.yml"),
    ):
        text = path.read_text(encoding="utf-8")
        assert "scripts/agentos_dispatch.sh" in text
        assert "submit_agentos_scheduler_request_https.sh" not in text


def test_dispatch_client_has_no_runner_or_worker_selector():
    text = Path("scripts/agentos_dispatch.sh").read_text(encoding="utf-8")
    assert "/v1/dispatch" in text
    assert "runner_window_dispatch=PASS" in text
    assert "oracle-gui" not in text
    assert "oracle-control" not in text


def test_oursong_activation_maps_to_fixed_bootstrap_action():
    intent, params = resolve_intent(
        "persona.runtime",
        "oursong.activate",
        source_commit="b" * 40,
        payload={},
    )
    assert intent.action == bc.ACTION_ACTIVATE_OURSONG_PERSONA
    assert params == {"source_commit": "b" * 40}
    assert public_intent_for_action(bc.ACTION_ACTIVATE_OURSONG_PERSONA) == {
        "capability": "persona.runtime",
        "operation": "oursong.activate",
    }
