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


def test_executor_job_submit_and_inspect_are_bounded_public_intents():
    submit, submit_params = resolve_intent(
        "agentos.executor",
        "job.submit",
        source_commit="d" * 40,
        payload={"job_type": "experience.regression"},
    )
    assert submit.action == bc.ACTION_EXECUTOR_JOB_SUBMIT
    assert submit_params == {
        "source_commit": "d" * 40,
        "job_type": "experience.regression",
    }
    inspect, inspect_params = resolve_intent(
        "agentos.executor",
        "job.inspect",
        source_commit="e" * 40,
        payload={"job_id": "action-12345678"},
    )
    assert inspect.action == bc.ACTION_EXECUTOR_JOB_INSPECT
    assert inspect_params == {
        "source_commit": "e" * 40,
        "job_id": "action-12345678",
    }


def test_runtime_repair_cleanup_preserves_failure_stage_trap():
    text = Path("scripts/repair_antigravity_relay_user.sh").read_text(encoding="utf-8")
    assert "cleanup()" in text
    assert 'antigravity_repair_stage=$REPAIR_STAGE' in text
    assert 'antigravity_repair_exit=${REPAIR_FAILURE_RC:-$rc}' in text
    assert "trap cleanup EXIT" in text
    assert "trap 'rm -rf \"$TMPDIR\"' EXIT" not in text


def test_runner_window_projects_bounded_failed_step_diagnostics():
    text = Path("agent_core/realm_server.py").read_text(encoding="utf-8")
    assert "'antigravity_repair_exit='" in text
    assert "'failed_steps': failed_steps[:8]" in text


def test_runtime_repair_emits_bounded_failure_line():
    text = Path("scripts/repair_antigravity_relay_user.sh").read_text(encoding="utf-8")
    assert "REPAIR_FAILURE_LINE" in text
    assert "trap 'REPAIR_FAILURE_RC=$?; REPAIR_FAILURE_LINE=$LINENO' ERR" in text
    assert 'antigravity_repair_line=' in text
    server = Path("agent_core/realm_server.py").read_text(encoding="utf-8")
    assert "'antigravity_repair_line='" in server


def test_runner_window_allows_bounded_deterministic_smoke_evidence():
    text = Path("agent_core/realm_server.py").read_text(encoding="utf-8")
    assert "'worktree_clean'" in text
    assert "'observed_head'" in text


def test_relay_status_is_bounded_public_intent():
    item, params = resolve_intent(
        "agentos.relay",
        "status",
        source_commit="a" * 40,
        payload={},
    )
    assert item.action == bc.ACTION_RELAY_STATUS
    assert params == {"source_commit": "a" * 40}


def test_relay_status_projection_is_fixed_marker_only():
    text = Path("agent_core/realm_server.py").read_text(encoding="utf-8")
    for marker in (
        "relay_status_antigravity_service=",
        "relay_status_action_service=",
        "relay_status_inbox_count=",
        "relay_status_processing_count=",
        "relay_status_receipts_count=",
        "relay_status_inbox_oldest_seconds=",
        "relay_status_processing_oldest_seconds=",
        "relay_status=",
    ):
        assert marker in text


def test_scheduler_status_is_bounded_public_intent():
    item, params = resolve_intent(
        "agentos.scheduler",
        "status",
        source_commit="b" * 40,
        payload={},
    )
    assert item.action == bc.ACTION_SCHEDULER_STATUS
    assert params == {"source_commit": "b" * 40}


def test_scheduler_status_projection_is_fixed_marker_only():
    text = Path("agent_core/realm_server.py").read_text(encoding="utf-8")
    for marker in (
        "scheduler_status_pending_count=",
        "scheduler_status_pending_oldest_seconds=",
        "scheduler_status_stalled_count=",
        "scheduler_status_receipts_count=",
        "scheduler_status_rejected_count=",
        "scheduler_status=",
    ):
        assert marker in text


def test_runner_window_rejects_unknown_intent():
    with pytest.raises(ValueError):
        resolve_intent("future.unknown", "run", source_commit="a" * 40, payload={})


def test_runner_window_rejects_unregistered_payload_keys():
    with pytest.raises(ValueError):
        resolve_intent("browser.gui", "smoke", source_commit="a" * 40, payload={"runner": "oracle-gui"})


def test_realm_scheduler_public_projection_keeps_bounded_executor_job_identity():
    text = Path("agent_core/realm_server.py").read_text(encoding="utf-8")
    assert "public_receipt['executor_job']" in text
    assert "'job_id'" in text
    assert "'job_type'" in text
    assert "'credential_exposed'" in text
    assert "public_receipt['executor_job_receipt']" in text
    assert "'classification'" in text
    assert "'stdout'" not in text.split("public_receipt['executor_job_receipt']", 1)[1].split("return {", 1)[0]
    assert "'stderr'" not in text.split("public_receipt['executor_job_receipt']", 1)[1].split("return {", 1)[0]


def test_runner_window_catalog_contains_stable_public_intents():
    items = {(x["capability"], x["operation"]) for x in catalog()}
    assert ("agentos.dispatch", "probe") in items
    assert ("agentos.runtime", "repair") in items
    assert ("browser.gui", "smoke") in items
    assert ("social.runtime", "deploy") in items
    assert ("social.publish", "mio.approved") in items
    assert ("persona.runtime", "oursong.activate") in items
    assert ("persona.runtime", "oursong.status") in items


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


def test_executor_job_public_intents_map_to_fixed_bootstrap_actions():
    submit, params = resolve_intent(
        "agentos.executor",
        "job.submit",
        source_commit="f" * 40,
        payload={"job_type": "engineering.windows-thin-client.fix"},
    )
    assert submit.action == bc.ACTION_EXECUTOR_JOB_SUBMIT
    assert params["job_type"] == "engineering.windows-thin-client.fix"
    inspect, params = resolve_intent(
        "agentos.executor",
        "job.inspect",
        source_commit="1" * 40,
        payload={"job_id": "action-12345678"},
    )
    assert inspect.action == bc.ACTION_EXECUTOR_JOB_INSPECT
    assert params["job_id"] == "action-12345678"


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

def test_oursong_status_maps_to_fixed_bootstrap_action():
    intent, params = resolve_intent(
        "persona.runtime",
        "oursong.status",
        source_commit="c" * 40,
        payload={},
    )
    assert intent.action == bc.ACTION_PROBE_OURSONG_PERSONA
    assert params == {"source_commit": "c" * 40}
    assert public_intent_for_action(bc.ACTION_PROBE_OURSONG_PERSONA) == {
        "capability": "persona.runtime",
        "operation": "oursong.status",
    }


def test_realm_scheduler_public_projection_keeps_bounded_executor_health_diagnostics():
    text = Path("agent_core/realm_server.py").read_text(encoding="utf-8")
    block = text.rsplit("elif action == bootstrap_control.ACTION_EXECUTOR_JOB_INSPECT:", 1)[1]
    block = block.split("return {", 1)[0]
    for field in (
        "'claude_health_classification'",
        "'agy_health_classification'",
        "'gemini_health_classification'",
        "'gemini_state'",
        "'gemini_ready_count'",
        "'runtime_source_commit'",
    ):
        assert field in block
    assert "'stdout'" not in block
    assert "'stderr'" not in block
