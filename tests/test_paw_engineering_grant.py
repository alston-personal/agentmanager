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

def test_trusted_issuer_rejects_absent_lease(tmp_path):
    from agentos_node.paw_engineering_request import issue_paw_request
    from pathlib import Path
    class Missing:
        def get_lease(self, assignment_id):
            return None
    with pytest.raises(PawWorktreeBoundaryError, match="paw_live_lease_not_authorized"):
        issue_paw_request(
            grant=grant(), expected_sha256="a" * 64,
            replacement="def test_x(): pass", issuer_key=b"k" * 32,
            trusted_assignment_id="paw-470-inspection-v1",
            trusted_wake_id=grant()["wake_id"],
            trusted_presence_generation=1, trusted_lease_generation=1,
            lifecycle=Missing(), trusted_lease_id="missing",
            registry_path=Path(__file__).resolve().parents[1] / "governance/execution-authority.json",
        )


def test_dynamic_paw_b_cannot_reuse_fixed_a_engineering_grant(tmp_path):
    """A's signed engineering identity cannot be substituted with B's assignment."""
    from pathlib import Path
    from agentos_node.paw_engineering_request import issue_paw_request
    payload = grant()
    payload["assignment_id"] = "paw-b"
    policy = Path(__file__).resolve().parents[1] / "governance/execution-authority.json"
    with pytest.raises(PawWorktreeBoundaryError, match="paw_grant_assignment_invalid"):
        validate_paw_engineering_grant(
            payload, expected_assignment_id="paw-b",
            expected_wake_id=payload["wake_id"],
            expected_presence_generation=1, expected_lease_generation=1,
        )
    with pytest.raises(PawWorktreeBoundaryError, match="paw_issuer_assignment_invalid"):
        issue_paw_request(
            grant=payload, expected_sha256="0" * 64,
            replacement="def test_ok(): pass", issuer_key=b"x" * 32,
            trusted_assignment_id="paw-b",
            trusted_wake_id=payload["wake_id"],
            trusted_presence_generation=1, trusted_lease_generation=1,
            lifecycle=object(), trusted_lease_id="lease-b", registry_path=policy,
        )


def test_dynamic_paw_binding_requires_exact_canonical_work_item(tmp_path):
    from agent_core.employee_runtime import EmployeeRuntime
    from agent_core.core_work_items import WORK_ITEM_SCHEMA, WorkItemStore
    from agentos_node.paw_engineering_grant import require_dynamic_paw_assignment_binding
    runtime = EmployeeRuntime(tmp_path)
    runtime.create_employee("the-paw", "Paw", role_ids=["sector.paw"],
                            skill_ids=["engineering.work.inspect"])
    store = WorkItemStore(runtime)
    store.persist({
        "schema": WORK_ITEM_SCHEMA, "work_item_id": "paw-b-work",
        "source_kind": "canonical_state", "source_ref": "task:paw-b-work",
        "project_id": "agentos-core", "employee_id": "the-paw",
        "assignment_id": "paw-b", "goal": "Inspect B",
        "required_capabilities": ["engineering.work.inspect"],
        "authority_requirements": ["one-governed-dispatch"], "state": "open",
    })
    store.project_pending_assignment("paw-b-work")
    require_dynamic_paw_assignment_binding(
        assignment_id="paw-b", work_item_id="paw-b-work", runtime=runtime,
    )
    with pytest.raises(PawWorktreeBoundaryError, match="paw_dynamic_binding_not_authorized"):
        require_dynamic_paw_assignment_binding(
            assignment_id="paw-470-inspection-v1", work_item_id="paw-b-work",
            runtime=runtime,
        )


def test_terminal_paw_publication_requires_committed_handoff_receipt(tmp_path):
    from agent_core.employee_runtime import EmployeeRuntime
    from agent_core.employee_lifecycle import EmployeeLifecycle
    from agent_core.core_work_items import WORK_ITEM_SCHEMA, WorkItemStore
    from agentos_node.paw_engineering_grant import require_dynamic_paw_assignment_binding

    runtime = EmployeeRuntime(tmp_path)
    runtime.create_employee("the-paw", "Paw", role_ids=["sector.paw"],
                            skill_ids=["engineering.work.inspect"])
    store = WorkItemStore(runtime)
    store.persist({
        "schema": WORK_ITEM_SCHEMA, "work_item_id": "work-b",
        "source_kind": "canonical_state", "source_ref": "task:work-b",
        "project_id": "agentos-core", "employee_id": "the-paw",
        "assignment_id": "paw-b", "goal": "Inspect B",
        "required_capabilities": ["engineering.work.inspect"],
        "authority_requirements": ["one-governed-dispatch"], "state": "open",
    })
    store.project_pending_assignment("work-b")
    lifecycle = EmployeeLifecycle(runtime)
    with pytest.raises(PawWorktreeBoundaryError):
        require_dynamic_paw_assignment_binding(
            assignment_id="paw-b", runtime=runtime, terminal_publication=True)
    lifecycle.claim("paw-b", "the-paw", "lease-b")
    lifecycle.finish("paw-b", "lease-b", state="handoff")
    require_dynamic_paw_assignment_binding(
        assignment_id="paw-b", runtime=runtime, terminal_publication=True)
    with pytest.raises(PawWorktreeBoundaryError, match="paw_dynamic_binding_not_authorized"):
        require_dynamic_paw_assignment_binding(assignment_id="paw-b", runtime=runtime)
    with pytest.raises(PawWorktreeBoundaryError, match="paw_dynamic_binding_ambiguous"):
        require_dynamic_paw_assignment_binding(
            assignment_id="paw-b", work_item_id="wrong-work", runtime=runtime,
            terminal_publication=True)
    import json
    receipt = lifecycle._receipt_path("paw-b", 1)
    original = receipt.read_text(encoding="utf-8")
    forged = json.loads(original)
    forged["lease_id"] = "forged-lease"
    receipt.write_text(json.dumps(forged), encoding="utf-8")
    with pytest.raises(PawWorktreeBoundaryError, match="paw_terminal_publication_receipt_invalid"):
        require_dynamic_paw_assignment_binding(
            assignment_id="paw-b", runtime=runtime, terminal_publication=True)
    forged["lease_id"] = "lease-b"
    forged["employee_id"] = "foreign-employee"
    receipt.write_text(json.dumps(forged), encoding="utf-8")
    with pytest.raises(PawWorktreeBoundaryError, match="paw_terminal_publication_receipt_invalid"):
        require_dynamic_paw_assignment_binding(
            assignment_id="paw-b", runtime=runtime, terminal_publication=True)
    receipt.write_text(original, encoding="utf-8")
    receipt = lifecycle._receipt_path("paw-b", 1)
    receipt.unlink()
    with pytest.raises(PawWorktreeBoundaryError, match="paw_terminal_publication_receipt_invalid"):
        require_dynamic_paw_assignment_binding(
            assignment_id="paw-b", runtime=runtime, terminal_publication=True)


def test_dynamic_paw_binding_denies_unverified_dependency(tmp_path):
    from agent_core.employee_runtime import EmployeeRuntime
    from agent_core.core_work_items import WORK_ITEM_SCHEMA, WorkItemStore
    from agentos_node.paw_engineering_grant import require_dynamic_paw_assignment_binding
    runtime = EmployeeRuntime(tmp_path)
    runtime.create_employee("the-paw", "Paw", role_ids=["sector.paw"],
                            skill_ids=["engineering.work.inspect"])
    store = WorkItemStore(runtime)
    store.persist({
        "schema": WORK_ITEM_SCHEMA, "work_item_id": "dependent-b",
        "source_kind": "canonical_state", "source_ref": "task:dependent-b",
        "project_id": "agentos-core", "employee_id": "the-paw",
        "assignment_id": "paw-b", "goal": "Do B",
        "dependency_refs": ["task:not-yet-done"],
        "required_capabilities": ["engineering.work.inspect"],
        "authority_requirements": ["one-governed-dispatch"], "state": "open",
    })
    store.project_pending_assignment("dependent-b")
    with pytest.raises(PawWorktreeBoundaryError, match="paw_dynamic_dependency_not_verified"):
        require_dynamic_paw_assignment_binding(
            assignment_id="paw-b", work_item_id="dependent-b", runtime=runtime,
        )


def test_dynamic_paw_binding_allows_receipt_verified_dependency(tmp_path):
    from agent_core.employee_runtime import EmployeeRuntime
    from agent_core.employee_lifecycle import EmployeeLifecycle
    from agent_core.core_work_items import WORK_ITEM_SCHEMA, WorkItemStore
    from agentos_node.paw_engineering_grant import require_dynamic_paw_assignment_binding
    runtime = EmployeeRuntime(tmp_path)
    runtime.create_employee("the-paw", "Paw", role_ids=["sector.paw"],
                            skill_ids=["engineering.work.inspect"])
    runtime.create_assignment("paw-a", "the-paw", "Do A")
    store = WorkItemStore(runtime)
    store.persist({
        "schema": WORK_ITEM_SCHEMA, "work_item_id": "dependency-a",
        "source_kind": "canonical_state", "source_ref": "task:dependency-a",
        "project_id": "agentos-core", "employee_id": "the-paw",
        "assignment_id": "paw-a", "goal": "Do A", "state": "open",
    })
    store.persist({
        "schema": WORK_ITEM_SCHEMA, "work_item_id": "dependent-b",
        "source_kind": "canonical_state", "source_ref": "task:dependent-b",
        "project_id": "agentos-core", "employee_id": "the-paw",
        "assignment_id": "paw-b", "goal": "Do B",
        "dependency_refs": ["task:dependency-a"],
        "required_capabilities": ["engineering.work.inspect"],
        "authority_requirements": ["one-governed-dispatch"], "state": "open",
    })
    store.project_pending_assignment("dependent-b")
    lifecycle = EmployeeLifecycle(runtime)
    lifecycle.claim("paw-a", "the-paw", "lease-a")
    lifecycle.finish("paw-a", "lease-a", state="completed",
                     result_summary={"test": "completed"})
    require_dynamic_paw_assignment_binding(
        assignment_id="paw-b", work_item_id="dependent-b", runtime=runtime,
    )


def test_dynamic_paw_binding_rejects_duplicate_assignment_work_items(tmp_path):
    from agent_core.employee_runtime import EmployeeRuntime
    from agent_core.core_work_items import WORK_ITEM_SCHEMA, WorkItemStore
    from agentos_node.paw_engineering_grant import require_dynamic_paw_assignment_binding
    runtime = EmployeeRuntime(tmp_path)
    runtime.create_employee("the-paw", "Paw", role_ids=["sector.paw"],
                            skill_ids=["engineering.work.inspect"])
    store = WorkItemStore(runtime)
    for work_item_id in ("paw-b-one", "paw-b-two"):
        store.persist({
            "schema": WORK_ITEM_SCHEMA, "work_item_id": work_item_id,
            "source_kind": "canonical_state", "source_ref": "task:" + work_item_id,
            "project_id": "agentos-core", "employee_id": "the-paw",
            "assignment_id": "paw-b", "goal": "Inspect B",
            "required_capabilities": ["engineering.work.inspect"],
            "authority_requirements": ["one-governed-dispatch"], "state": "open",
        })
    store.project_pending_assignment("paw-b-one")
    with pytest.raises(PawWorktreeBoundaryError, match="paw_dynamic_binding_ambiguous"):
        require_dynamic_paw_assignment_binding(
            assignment_id="paw-b", work_item_id="paw-b-one", runtime=runtime,
        )


def test_dynamic_b_requires_explicit_trusted_runtime_opt_in():
    b = grant()
    b["assignment_id"] = "paw-b"
    kwargs = dict(expected_assignment_id="paw-b", expected_wake_id=b["wake_id"],
                  expected_presence_generation=1, expected_lease_generation=1)
    with pytest.raises(PawWorktreeBoundaryError, match="paw_grant_assignment_invalid"):
        validate_paw_engineering_grant(b, **kwargs)
    validated = validate_paw_engineering_grant(b, allow_dynamic_assignment=True, **kwargs)
    assert validated.assignment_id == "paw-b"
    forged = dict(b, assignment_id="paw-a")
    with pytest.raises(PawWorktreeBoundaryError, match="paw_grant_wake_mismatch"):
        validate_paw_engineering_grant(forged, allow_dynamic_assignment=True, **kwargs)


def test_dynamic_b_signed_request_requires_verified_workitem_and_own_lease(tmp_path):
    """Real signed B request through existing runtime, policy and lifecycle gates."""
    from pathlib import Path
    from agent_core.employee_runtime import EmployeeRuntime
    from agent_core.employee_lifecycle import EmployeeLifecycle
    from agent_core.core_work_items import WorkItemStore, WORK_ITEM_SCHEMA
    from agentos_node.paw_engineering_request import issue_paw_request, authenticate_paw_request

    runtime = EmployeeRuntime(tmp_path / "runtime")
    runtime.create_employee("the-paw", "Paw", role_ids=["sector.paw"],
                            skill_ids=["engineering.work.inspect"])
    store = WorkItemStore(runtime)
    source_a = "task:a"
    store.persist({
        "schema": WORK_ITEM_SCHEMA, "work_item_id": "work-a",
        "source_kind": "canonical_state", "source_ref": source_a,
        "project_id": "agentos-core", "employee_id": "the-paw",
        "assignment_id": "paw-a", "goal": "Complete A",
        "state": "open",
    })
    store.project_pending_assignment("work-a")
    store.persist({
        "schema": WORK_ITEM_SCHEMA, "work_item_id": "work-b",
        "source_kind": "canonical_state", "source_ref": "task:b",
        "project_id": "agentos-core", "employee_id": "the-paw",
        "assignment_id": "paw-b", "goal": "B after A",
        "dependency_refs": [source_a],
        "required_capabilities": ["engineering.work.inspect"],
        "authority_requirements": ["one-governed-dispatch"], "state": "open",
    })
    store.project_pending_assignment("work-b")
    lifecycle = EmployeeLifecycle(runtime)
    lease = lifecycle.claim("paw-b", "the-paw", "lease-b", lease_seconds=300)
    b = dict(grant(), assignment_id="paw-b", work_id="issue-470-b")
    registry = Path(__file__).resolve().parents[1] / "governance/execution-authority.json"
    args = dict(grant=b, expected_sha256="a" * 64, replacement="safe",
                issuer_key=b"test-trusted-issuer-key-longer-than-32-bytes",
                trusted_assignment_id="paw-b", trusted_wake_id=b["wake_id"],
                trusted_presence_generation=1, trusted_lease_generation=lease.generation,
                lifecycle=lifecycle, trusted_lease_id="lease-b", registry_path=registry,
                trusted_runtime=runtime)
    with pytest.raises(PawWorktreeBoundaryError, match="paw_dynamic_dependency_not_verified"):
        issue_paw_request(**args)
    lifecycle.claim("paw-a", "the-paw", "lease-a", lease_seconds=300)
    lifecycle.finish("paw-a", "lease-a", state="completed")
    signed = issue_paw_request(**args)
    assert authenticate_paw_request(signed, issuer_key=args["issuer_key"])["grant"]["assignment_id"] == "paw-b"
    with pytest.raises(PawWorktreeBoundaryError):
        issue_paw_request(**dict(args, trusted_lease_id="lease-a"))
    with pytest.raises(PawWorktreeBoundaryError):
        issue_paw_request(**dict(args, trusted_runtime=None))


def test_trusted_request_filename_separates_assignments_and_rejects_paths():
    from agentos_node.paw_engineering_request import trusted_request_filename
    assert trusted_request_filename("paw-470-inspection-v1") == "paw-470-request.json"
    first = trusted_request_filename("paw-work-a")
    second = trusted_request_filename("paw-work-b")
    assert first != second
    assert first.startswith("paw-request-") and first.endswith(".json")
    assert "/" not in first and "\\\\" not in first
    assert trusted_request_filename("paw-work-a") == first
    for unsafe in ("../evil", "paw/a", "", "A" * 200):
        with pytest.raises(PawWorktreeBoundaryError):
            trusted_request_filename(unsafe)


def test_trusted_issuer_publishes_once_without_overwriting(tmp_path):
    import hashlib
    import hmac
    import json
    import os
    from agentos_node.paw_engineering_request import (
        canonical_payload, publish_trusted_paw_request, read_authenticated_paw_request,
    )
    directory = tmp_path / "issuer"
    directory.mkdir(mode=0o700)
    key = b"k" * 32
    body = {
        "schema": "agentos.paw-engineering-request/v1",
        "grant": grant(), "expected_sha256": hashlib.sha256(b"test").hexdigest(),
        "replacement": "test", "signature": "",
    }
    body["signature"] = hmac.new(key, canonical_payload(body), hashlib.sha256).hexdigest()
    path = publish_trusted_paw_request(
        directory, assignment_id="paw-470-inspection-v1",
        signed_request=body, issuer_key=key,
    )
    assert read_authenticated_paw_request(path, issuer_key=key) == body
    assert path.stat().st_mode & 0o077 == 0
    with pytest.raises(PawWorktreeBoundaryError, match="already_exists"):
        publish_trusted_paw_request(
            directory, assignment_id="paw-470-inspection-v1",
            signed_request=body, issuer_key=key,
        )
    assert read_authenticated_paw_request(path, issuer_key=key) == body
    with pytest.raises(PawWorktreeBoundaryError, match="assignment_invalid"):
        publish_trusted_paw_request(
            directory, assignment_id="paw-b", signed_request=body, issuer_key=key,
        )
    os.chmod(directory, 0o755)
    with pytest.raises(PawWorktreeBoundaryError, match="directory_not_trusted"):
        publish_trusted_paw_request(
            directory, assignment_id="paw-470-inspection-v1",
            signed_request=body, issuer_key=key,
        )
