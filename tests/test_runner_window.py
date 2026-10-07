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



def test_control_inbox_reconcile_is_bounded_public_intent():
    intent, params = resolve_intent(
        "agentos.control-inbox",
        "reconcile",
        source_commit="8" * 40,
        payload={},
    )
    assert intent.action == bc.ACTION_RECONCILE_CONTROL_INBOX
    assert params == {"source_commit": "8" * 40}
    assert public_intent_for_action(bc.ACTION_RECONCILE_CONTROL_INBOX) == {
        "capability": "agentos.control-inbox",
        "operation": "reconcile",
    }

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
    assert ("agentos.control-inbox", "reconcile") in items
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
        "'runtime_source_commit'",
    ):
        assert field in block
    assert "'stdout'" not in block
    assert "'stderr'" not in block

def test_realm_node_public_intents_are_bounded():
    inspect, inspect_params = resolve_intent(
        "node.realm",
        "inspect",
        source_commit="2" * 40,
        payload={"node_id": "vopc5750"},
    )
    assert inspect.action == bc.ACTION_REALM_NODE_INSPECT
    assert inspect_params == {"source_commit": "2" * 40, "node_id": "vopc5750"}

    probe, probe_params = resolve_intent(
        "node.desktop",
        "probe",
        source_commit="3" * 40,
        payload={"node_id": "vopc5750"},
    )
    assert probe.action == bc.ACTION_REALM_DESKTOP_PROBE
    assert probe_params == {"source_commit": "3" * 40, "node_id": "vopc5750"}


def test_realm_node_public_projection_is_bounded():
    text = Path("agent_core/realm_server.py").read_text(encoding="utf-8")
    for marker in (
        "realm_node_status=",
        "realm_node_heartbeat_age_seconds=",
        "realm_node_desktop_capable=",
        "realm_node_runtime_status=",
        "realm_node_runtime_source_commit=",
        "realm_desktop_probe=",
    ):
        assert marker in text
    assert "token_hash" not in text.split("ACTION_REALM_NODE_INSPECT", 1)[1].split("ACTION_NODE_TRANSACTIONAL_OTA", 1)[0]

def test_google_media_generation_public_intents_are_bounded():
    flow, flow_params = resolve_intent(
        "media.google-flow",
        "generate",
        source_commit="4" * 40,
        payload={"prompt": "test scene"},
    )
    assert flow.action == bc.ACTION_GOOGLE_FLOW_GENERATE
    assert flow_params == {"source_commit": "4" * 40, "prompt": "test scene"}

    vids, vids_params = resolve_intent(
        "media.google-vids",
        "generate",
        source_commit="5" * 40,
        payload={"prompt": "test scene"},
    )
    assert vids.action == bc.ACTION_GOOGLE_VIDS_GENERATE
    assert vids_params == {"source_commit": "5" * 40, "prompt": "test scene"}

def test_vision_studio_produce_public_intent_is_bounded():
    intent, params = resolve_intent(
        "media.vision-studio",
        "produce",
        source_commit="6" * 40,
        payload={"project_id": "rain-exit-v001"},
    )
    assert intent.action == bc.ACTION_VISION_STUDIO_PRODUCE
    assert params == {"source_commit": "6" * 40, "project_id": "rain-exit-v001"}
    assert public_intent_for_action(bc.ACTION_VISION_STUDIO_PRODUCE) == {
        "capability": "media.vision-studio",
        "operation": "produce",
    }


def test_browser_gui_install_public_intent():
    intent, params = resolve_intent(
        "browser.gui",
        "install",
        source_commit="6" * 40,
        payload={},
    )
    assert intent.action == bc.ACTION_INSTALL_GUI_WORKER
    assert params == {"source_commit": "6" * 40}



def test_realm_executor_reconcile_is_bounded_public_intent():
    intent, params = resolve_intent(
        "node.executor",
        "reconcile",
        source_commit="7" * 40,
        payload={"node_id": "vopc5750"},
    )
    assert intent.action == bc.ACTION_REALM_EXECUTOR_RECONCILE
    assert params == {"source_commit": "7" * 40, "node_id": "vopc5750"}
    assert public_intent_for_action(bc.ACTION_REALM_EXECUTOR_RECONCILE) == {
        "capability": "node.executor",
        "operation": "reconcile",
    }


def test_realm_executor_reconcile_public_projection_is_bounded():
    text = Path("agent_core/realm_server.py").read_text(encoding="utf-8")
    for marker in (
        "realm_executor_reconcile=",
        "realm_executor_codex_state=",
        "realm_executor_gemini_state=",
        "realm_executor_claude_code_state=",
    ):
        assert marker in text


def test_realm_node_runtime_provenance_is_bounded_to_identity_fields():
    text = Path("agentos_node/bootstrap_control.py").read_text(encoding="utf-8")
    block = text.split("def _realm_node_inspect", 1)[1].split("def _realm_desktop_probe", 1)[0]
    assert "realm_node_runtime_status=" in block
    assert "realm_node_runtime_source_commit=" in block
    assert "provenance_path" not in block


def test_vision_studio_scheduler_policy():
    from agentos_node.bootstrap_scheduler import policy_for
    policy = policy_for(bc.ACTION_VISION_STUDIO_PRODUCE)
    assert policy.role == "gui"
    assert "media.vision-studio.produce" in policy.capabilities
    assert "oracle-gui-profile" in policy.locks


def test_github_actions_dispatch_is_bounded_public_intent():
    intent, params = resolve_intent(
        "github.actions",
        "workflow.dispatch",
        source_commit="9" * 40,
        payload={
            "workflow": "oursong-persona-activation.yml",
            "ref": "core/integration",
            "inputs": {},
        },
    )
    assert intent.action == bc.ACTION_GITHUB_ACTIONS_DISPATCH
    assert params == {
        "source_commit": "9" * 40,
        "workflow": "oursong-persona-activation.yml",
        "ref": "core/integration",
        "inputs": {},
    }
    with pytest.raises(ValueError):
        resolve_intent(
            "github.actions",
            "workflow.dispatch",
            source_commit="9" * 40,
            payload={"repository": "attacker/repo"},
        )



def test_threads_dm_read_public_projection_keeps_identity_without_message_content():
    text = Path("agent_core/realm_server.py").read_text(encoding="utf-8")
    for marker in (
        "threads_web_dm_identity=",
        "threads_web_dm_account=",
        "threads_web_dm_read=",
    ):
        assert marker in text
    block = text.split("bootstrap_control.ACTION_READ_OURSONG_THREADS_WEB_DM", 1)[1]
    block = block.split("elif action == bootstrap_control.ACTION_INSTALL_MIO_THREADS_SESSION_SUPERVISOR", 1)[0]
    assert "message_id=" not in block
    assert "conversation_id=" not in block
    assert "actor_username=" not in block


def test_threads_dm_login_start_public_projection_is_bounded():
    text = Path("agent_core/realm_server.py").read_text(encoding="utf-8")
    for marker in (
        "threads_web_dm_login_start=",
        "threads_web_dm_login_mode=",
        "threads_web_dm_login_browser_persistent=",
        "threads_web_dm_login_remote_view=",
        "threads_web_dm_login_transport=",
    ):
        assert marker in text

def test_oursong_dm_read_is_bounded_and_separate_from_mio():
    intent, params = resolve_intent(
        "persona.social.dm",
        "oursong.read",
        source_commit="a" * 40,
        payload={},
    )
    assert intent.action == bc.ACTION_READ_OURSONG_THREADS_WEB_DM
    assert params == {"source_commit": "a" * 40}
    from agentos_node.bootstrap_scheduler import policy_for
    oursong = policy_for(bc.ACTION_READ_OURSONG_THREADS_WEB_DM)
    mio = policy_for(bc.ACTION_READ_THREADS_WEB_DM)
    assert "threads-oursong-gui" in oursong.locks
    assert "threads-mio-gui" in mio.locks
    assert oursong.locks != mio.locks


def test_oursong_threads_session_intents_are_isolated():
    install, params = resolve_intent(
        "persona.social.dm",
        "oursong.session.install",
        source_commit="d" * 40,
        payload={},
    )
    assert install.action == bc.ACTION_INSTALL_OURSONG_THREADS_SESSION
    assert params == {"source_commit": "d" * 40}

    login, params = resolve_intent(
        "persona.social.dm",
        "oursong.login.start",
        source_commit="e" * 40,
        payload={},
    )
    assert login.action == bc.ACTION_START_OURSONG_THREADS_WEB_DM_LOGIN
    assert params == {"source_commit": "e" * 40}

    from agentos_node.bootstrap_scheduler import policy_for
    login_policy = policy_for(bc.ACTION_START_OURSONG_THREADS_WEB_DM_LOGIN)
    assert "threads-oursong-gui" in login_policy.locks
    assert "threads-mio-gui" not in login_policy.locks


def test_persona_dm_bindings_use_distinct_cdp_sessions():
    from agentos_node.social.persona_dm import binding_for
    mio = binding_for("mio")
    oursong = binding_for("oursong")
    assert mio.cdp_url == "http://127.0.0.1:9222"
    assert oursong.cdp_url == "http://127.0.0.1:9223"
    assert mio.profile_key != oursong.profile_key


def test_oursong_mio_dm_roundtrip_intent_is_bounded():
    intent, params = resolve_intent(
        "persona.social.dm",
        "oursong.roundtrip.mio",
        source_commit="f" * 40,
        payload={},
    )
    assert intent.action == bc.ACTION_ACCEPT_OURSONG_DM_MIO_ROUNDTRIP
    assert params == {"source_commit": "f" * 40}
    from agentos_node.bootstrap_scheduler import policy_for
    policy = policy_for(bc.ACTION_ACCEPT_OURSONG_DM_MIO_ROUNDTRIP)
    assert "threads-mio-gui" in policy.locks
    assert "threads-oursong-gui" in policy.locks
    assert "persona.social.dm.roundtrip" in policy.capabilities
