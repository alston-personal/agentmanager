from pathlib import Path

from agent_core.runner_window import resolve_intent
from agentos_node import bootstrap_control as bc
from agentos_node.bootstrap_scheduler import policy_for


def test_node_ota_public_intent_maps_to_governed_action():
    intent, params = resolve_intent(
        "node.runtime",
        "transactional-ota",
        source_commit="a" * 40,
        payload={"node_id": "vopc5750", "candidate_commit": "b" * 40},
    )
    assert intent.action == bc.ACTION_NODE_TRANSACTIONAL_OTA
    assert params == {
        "source_commit": "a" * 40,
        "node_id": "vopc5750",
        "candidate_commit": "b" * 40,
    }


def test_node_ota_scheduler_is_control_plane_routed():
    policy = policy_for(bc.ACTION_NODE_TRANSACTIONAL_OTA)
    assert policy.role == "control"
    assert "node.runtime.ota" in set(policy.capabilities)
    assert "node-runtime-ota" in set(policy.locks)


def test_vopc_workflow_never_selects_self_hosted_runner():
    text = Path(".github/workflows/oracle-vopc5750-transactional-ota.yml").read_text(encoding="utf-8")
    assert "uses: ./.github/workflows/agentos-dispatch.yml" in text
    assert "capability: node.runtime" in text
    assert "operation: transactional-ota" in text
    assert "runs-on: [self-hosted" not in text
    assert "oracle]" not in text


def test_vopc_live_ota_requires_explicit_command_change():
    text = Path(".github/workflows/oracle-vopc5750-transactional-ota.yml").read_text(encoding="utf-8")
    push = text.split("permissions:", 1)[0]
    assert ".agentos/commands/realm-node-transactional-ota.json" in push
    assert ".github/workflows/oracle-vopc5750-transactional-ota.yml" not in push
    assert "scripts/run_realm_node_transactional_ota_user.sh" not in push


def test_break_glass_repair_is_manual_only():
    text = Path(".github/workflows/oracle-one-break-glass-repair.yml").read_text(encoding="utf-8")
    head = text.split("permissions:", 1)[0]
    assert "workflow_dispatch:" in head
    assert "\n  push:" not in head
