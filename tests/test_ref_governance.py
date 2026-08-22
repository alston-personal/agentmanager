import pytest
from runtime_core.ref_governance import RefGovernanceError, RefMoveIntent, authorize_ref_move


def make_intent(**changes):
    data = dict(repository="alston-personal/agentmanager", ref="feature/distributed-agentos-runtime", old_sha="base123", new_sha="head456", actor_ref="executor-b", reason="workflow bootstrap", explicit_human_approval=False, is_fast_forward=True, open_pr_head_shas=("head456",), integration_refs=("feature/distributed-agentos-runtime",))
    data.update(changes)
    return RefMoveIntent(**data)


def test_integration_ref_cannot_absorb_pr_head_without_approval():
    with pytest.raises(RefGovernanceError, match="merge-equivalent"):
        authorize_ref_move(make_intent())


def test_approved_merge_equivalent_move_is_allowed():
    authorize_ref_move(make_intent(explicit_human_approval=True))


def test_unrelated_fast_forward_is_allowed():
    authorize_ref_move(make_intent(new_sha="other789"))


def test_non_fast_forward_is_denied():
    with pytest.raises(RefGovernanceError, match="break-glass"):
        authorize_ref_move(make_intent(is_fast_forward=False, explicit_human_approval=True))


def test_main_is_protected_by_default():
    with pytest.raises(RefGovernanceError, match="merge-equivalent"):
        authorize_ref_move(make_intent(ref="main", integration_refs=()))
