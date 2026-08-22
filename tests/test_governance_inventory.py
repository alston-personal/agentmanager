from agent_core.governance import GovernanceGate
from agent_core.governance_inventory import audit_inventory, current_inventory


def test_current_capability_inventory_has_no_policy_coverage_errors():
    assert audit_inventory() == ()


def test_every_inventory_capability_is_unique():
    names = [entry.profile.capability for entry in current_inventory()]
    assert len(names) == len(set(names))


def test_browser_and_autonomous_external_surfaces_remain_fail_closed():
    entries = {entry.profile.capability: entry for entry in current_inventory()}
    gate = GovernanceGate()
    assert gate.evaluate(entries["browser.gemini.shadow"].profile).allowed is False
    assert gate.evaluate(entries["node.external.act"].profile).allowed is False
    assert gate.evaluate(entries["agent.autonomous.external"].profile).allowed is False


def test_state_and_cognition_surfaces_have_governed_authority():
    entries = {entry.profile.capability: entry for entry in current_inventory()}
    gate = GovernanceGate()
    for name in (
        "project.state.read",
        "project.state.commit",
        "cognitive.synthesis",
        "cognitive.promote.project",
        "cognitive.promote.cross_project",
        "work.continue.select",
    ):
        assert gate.evaluate(entries[name].profile).allowed is True
