import pytest

from runtime_core.resume_contract import ResumeContract, restore_execution_disposition


def test_active_goal_resumes_without_new_user_turn():
    contract = ResumeContract(
        project_id="agentmanager",
        goal="Complete LCCB experiment",
        execution_state="EXECUTING",
        current_step="run_fixed_model_series",
        next_action="invoke_oracle_provider_runner",
        preferred_execution_path=["github-actions", "oracle-self-hosted", "openai-compatible"],
        capability_bindings=["github.write", "github.actions", "provider.chat"],
    )
    restored = restore_execution_disposition({"resume_contract": contract.to_dict()})
    assert restored is not None
    assert restored.should_continue is True
    assert restored.requires_human is False
    assert restored.next_action == "invoke_oracle_provider_runner"


def test_human_authority_is_terminal_for_autonomous_resume():
    contract = ResumeContract(
        project_id="agentmanager",
        goal="Complete LCCB experiment",
        execution_state="BLOCKED_HUMAN_AUTHORITY",
        current_step="credential_authorization",
        next_action="request_human_authority",
    )
    assert contract.should_continue is False
    assert contract.requires_human is True


def test_active_contract_requires_next_action():
    with pytest.raises(ValueError):
        ResumeContract(
            project_id="agentmanager",
            goal="Complete LCCB experiment",
            execution_state="EXECUTING",
            current_step="run",
            next_action="",
        )
