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

def test_executor_denies_without_live_lease_before_worktree_creation(tmp_path):
    from pathlib import Path
    from agentos_node.paw_engineering_executor import run_authorized_static_candidate

    class NoLease:
        def get_lease(self, assignment_id):
            return None

    workspace = tmp_path / "isolated"
    workspace.mkdir()
    policy = Path(__file__).resolve().parents[1] / "governance/execution-authority.json"
    with pytest.raises(PawWorktreeBoundaryError, match="paw_live_lease_not_authorized"):
        run_authorized_static_candidate(
            grant_payload=grant(),
            trusted_wake_id=grant()["wake_id"],
            trusted_presence_generation=1,
            trusted_lease_generation=1,
            trusted_lease_id="no-valid-lease",
            lifecycle=NoLease(),
            registry_path=policy,
            repository=tmp_path / "does-not-exist",
            workspace_root=workspace,
            expected_sha256="0" * 64,
            replacement="def test_ok():\n    assert True\n",
        )
    assert list(workspace.iterdir()) == []


def test_authorized_executor_creates_real_isolated_local_commit(tmp_path):
    """Exercise full canonical policy + live lease + git worktree + candidate commit."""
    import hashlib
    import subprocess
    from pathlib import Path
    from types import SimpleNamespace
    from agentos_node.paw_engineering_executor import run_authorized_static_candidate

    def git(root, *args):
        return subprocess.run(
            ["git", "-C", str(root), *args], check=True, text=True,
            capture_output=True,
        ).stdout.strip()

    repo = tmp_path / "repository"
    repo.mkdir()
    git(repo, "init")
    git(repo, "config", "user.email", "test@example.invalid")
    git(repo, "config", "user.name", "Fixture")
    source = repo / "tests/test_paw_engineering_worktree.py"
    source.parent.mkdir()
    source.write_text("def test_one():\n    assert True\n")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "fixture")
    base_sha = git(repo, "rev-parse", "HEAD")
    payload = grant()
    payload["base_sha"] = base_sha
    lease_id = "product-paw_inspect_v1-" + payload["wake_id"] + "-1"
    lease = SimpleNamespace(
        assignment_id=payload["assignment_id"], employee_id="the-paw",
        lease_id=lease_id, generation=1, status="active",
        resume_required=False, prior_execution_state="known",
    )

    class Lifecycle:
        def get_lease(self, assignment_id):
            return lease

        def lease_expired(self, current):
            return False

    root = tmp_path / "worktrees"
    root.mkdir()
    policy = Path(__file__).resolve().parents[1] / "governance/execution-authority.json"
    result = run_authorized_static_candidate(
        grant_payload=payload,
        trusted_wake_id=payload["wake_id"],
        trusted_presence_generation=1,
        trusted_lease_generation=1,
        trusted_lease_id=lease_id,
        lifecycle=Lifecycle(),
        registry_path=policy,
        repository=repo,
        workspace_root=root,
        expected_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        replacement="def test_one():\n    assert True\n\ndef test_two():\n    assert 2 + 2 == 4\n",
    )
    assert result.schema == "agentos.paw-local-commit-receipt/v1"
    assert result.published is False
    assert result.independent_acceptance_pass is False
    assert git(repo, "rev-parse", "HEAD") == base_sha
    assert source.read_text() == "def test_one():\n    assert True\n"
    assert git(root / payload["work_id"], "rev-parse", "HEAD") == result.commit_sha

def test_signed_request_rejects_forgery_before_any_execution():
    import hashlib
    import hmac
    from agentos_node.paw_engineering_request import (
        SCHEMA, authenticate_paw_request, canonical_payload,
    )
    from agentos_node.paw_engineering_executor import run_signed_paw_candidate
    key = b"control-plane-authority-key-at-least-32-bytes"
    request = {
        "schema": SCHEMA, "grant": grant(),
        "expected_sha256": "a" * 64,
        "replacement": "def test_ok():\\n    assert True\\n",
        "signature": "",
    }
    request["signature"] = hmac.new(key, canonical_payload(request), hashlib.sha256).hexdigest()
    assert authenticate_paw_request(request, issuer_key=key)["grant"] == grant()
    altered = dict(request)
    altered["replacement"] = "def test_bad():\\n    assert False\\n"
    with pytest.raises(PawWorktreeBoundaryError, match="authentication_failed"):
        authenticate_paw_request(altered, issuer_key=key)
    with pytest.raises(PawWorktreeBoundaryError, match="authentication_failed"):
        run_signed_paw_candidate(request=altered, issuer_key=key)
