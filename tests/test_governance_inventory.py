from agent_core.governance import GovernanceGate
from agent_core.governance_inventory import audit_inventory, current_inventory


def test_current_capability_inventory_has_no_policy_coverage_errors():
    assert audit_inventory() == ()


def test_every_inventory_capability_is_unique_and_grounded():
    entries = current_inventory()
    names = [entry.profile.capability for entry in entries]
    assert len(names) == len(set(names))
    assert all(entry.evidence_refs for entry in entries)


def test_under_governed_surfaces_remain_fail_closed():
    entries = {entry.profile.capability: entry for entry in current_inventory()}
    gate = GovernanceGate()
    for name in (
        "project.state.commit",
        "browser.gemini.shadow",
        "node.external.act",
        "agent.autonomous.external",
    ):
        assert gate.evaluate(entries[name].profile).allowed is False


def test_current_read_cognition_and_selection_surfaces_have_governed_authority():
    entries = {entry.profile.capability: entry for entry in current_inventory()}
    gate = GovernanceGate()
    for name in (
        "project.state.read",
        "cognitive.synthesis",
        "cognitive.promote.project",
        "cognitive.promote.cross_project",
        "work.continue.select",
    ):
        assert gate.evaluate(entries[name].profile).allowed is True
