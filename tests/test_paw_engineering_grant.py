import pytest
from agentos_node.paw_engineering_grant import validate_paw_engineering_grant, require_canonical_paw_authority, require_live_paw_lease
from agentos_node.paw_engineering_worktree import PawWorktreeBoundaryError


def grant():
    return {
        "schema": "agentos.paw-engineering-grant/v1",
        "work_id": "issue-470-a",
        "assignment_id": "paw-470-inspection-v1",
        "wake_id": "wake_" + "a" * 24,
        "presence_generation": 1, "lease_generation": 1,
        "repository_id": "alston-personal/agentmanager",
        "base_sha": "b" * 40,
        "allowed_path": "tests/test_paw_engineering_worktree.py",
        "action": "prepare-static-test-candidate",
    }


def validate(p):
    return validate_paw_engineering_grant(
        p, expected_assignment_id="paw-470-inspection-v1",
        expected_wake_id="wake_" + "a" * 24,
        expected_presence_generation=1, expected_lease_generation=1,
    )


def test_exact_grant_is_only_a_validated_candidate():
    assert validate(grant()).work_id == "issue-470-a"


@pytest.mark.parametrize("field, value", [
    ("schema", "v2"), ("repository_id", "someone/else"),
    ("allowed_path", "agentos_node/product_employee_worker.py"),
    ("action", "deploy"), ("base_sha", "main"),
    ("assignment_id", "another"), ("wake_id", "wake_" + "c" * 24),
    ("presence_generation", 2), ("lease_generation", 2),
    ("presence_generation", True), ("work_id", "../main"),
])
def test_grant_is_fail_closed(field, value):
    g = grant()
    g[field] = value
    with pytest.raises(PawWorktreeBoundaryError):
        validate(g)


def test_extra_fields_denied():
    g = grant()
    g["shell"] = "sh"
    with pytest.raises(PawWorktreeBoundaryError, match="shape_invalid"):
        validate(g)


def test_canonical_authority_admits_only_existing_policy():
    from pathlib import Path
    policy = Path(__file__).resolve().parents[1] / "governance/execution-authority.json"
    candidate = validate(grant())
    require_canonical_paw_authority(candidate, registry_path=policy)
    with pytest.raises(RuntimeError, match="source_ref_not_allowed"):
        require_canonical_paw_authority(candidate, registry_path=policy, source_ref="main")


def test_canonical_authority_rejects_policy_without_paw(tmp_path):
    import json
    from pathlib import Path
    policy = json.loads((Path(__file__).resolve().parents[1] / "governance/execution-authority.json").read_text())
    policy["capabilities"].pop("paw.engineering.candidate.prepare")
    fixture = tmp_path / "policy.json"
    fixture.write_text(json.dumps(policy))
    with pytest.raises(RuntimeError, match="authority_missing"):
        require_canonical_paw_authority(validate(grant()), registry_path=fixture)


def test_live_lease_rejects_missing_lifecycle():
    class MissingLifecycle:
        def get_lease(self, assignment_id):
            return None
    with pytest.raises(PawWorktreeBoundaryError, match="paw_live_lease_not_authorized"):
        require_live_paw_lease(validate(grant()), lifecycle=MissingLifecycle(), expected_lease_id="absent")
