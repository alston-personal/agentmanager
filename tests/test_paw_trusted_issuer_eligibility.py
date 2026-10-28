import pytest
from types import SimpleNamespace
from agentos_node.paw_engineering_worktree import PawWorktreeBoundaryError
import agentos_node.paw_trusted_issuer_eligibility as probe


def test_issuer_eligibility_requires_canonical_binding_and_live_known_lease(monkeypatch, tmp_path):
    monkeypatch.setattr(probe, "EmployeeRuntime", lambda root: object())
    lease = SimpleNamespace(
        assignment_id="paw-b", employee_id="the-paw",
        lease_id="lease-b", generation=3, status="active",
        resume_required=False, prior_execution_state="known",
    )
    holder = {"lease": lease}
    class Lifecycle:
        def __init__(self, runtime): pass
        def get_lease(self, assignment_id): return holder["lease"]
        def lease_expired(self, value): return False
    monkeypatch.setattr(probe, "EmployeeLifecycle", Lifecycle)
    seen = []
    monkeypatch.setattr(
        probe, "require_dynamic_paw_assignment_binding",
        lambda **kwargs: seen.append(kwargs["assignment_id"]),
    )
    result = probe.inspect_trusted_paw_lease(tmp_path, "paw-b", "lease-b")
    assert result["authorized_to_sign"] is False
    assert result["lease_generation"] == 3
    assert seen == ["paw-b"]
    with pytest.raises(PawWorktreeBoundaryError):
        probe.inspect_trusted_paw_lease(tmp_path, "paw-b", "wrong-lease")
    holder["lease"] = SimpleNamespace(**{**vars(lease), "resume_required": True})
    with pytest.raises(PawWorktreeBoundaryError):
        probe.inspect_trusted_paw_lease(tmp_path, "paw-b", "lease-b")


@pytest.mark.parametrize("mutation", [
    {"employee_id": "zeus-writer"},
    {"status": "completed"},
    {"prior_execution_state": "unknown"},
    {"assignment_id": "paw-other"},
    {"lease_id": "lease-other"},
])
def test_issuer_eligibility_rejects_ineligible_lease(monkeypatch, tmp_path, mutation):
    monkeypatch.setattr(probe, "EmployeeRuntime", lambda root: object())
    original = dict(
        assignment_id="paw-b", employee_id="the-paw",
        lease_id="lease-b", generation=3, status="active",
        resume_required=False, prior_execution_state="known",
    )
    class Lifecycle:
        def __init__(self, runtime): pass
        def get_lease(self, assignment_id):
            return SimpleNamespace(**{**original, **mutation})
        def lease_expired(self, lease): return False
    monkeypatch.setattr(probe, "EmployeeLifecycle", Lifecycle)
    monkeypatch.setattr(probe, "require_dynamic_paw_assignment_binding", lambda **kwargs: None)
    with pytest.raises(PawWorktreeBoundaryError, match="paw_issuer_live_lease_not_authorized"):
        probe.inspect_trusted_paw_lease(tmp_path, "paw-b", "lease-b")


def test_issuer_eligibility_rejects_expired_lease(monkeypatch, tmp_path):
    monkeypatch.setattr(probe, "EmployeeRuntime", lambda root: object())
    class Lifecycle:
        def __init__(self, runtime): pass
        def get_lease(self, assignment_id):
            return SimpleNamespace(
                assignment_id=assignment_id, employee_id="the-paw",
                lease_id="lease-b", generation=3, status="active",
                resume_required=False, prior_execution_state="known",
            )
        def lease_expired(self, lease): return True
    monkeypatch.setattr(probe, "EmployeeLifecycle", Lifecycle)
    monkeypatch.setattr(probe, "require_dynamic_paw_assignment_binding", lambda **kwargs: None)
    with pytest.raises(PawWorktreeBoundaryError, match="paw_issuer_live_lease_not_authorized"):
        probe.inspect_trusted_paw_lease(tmp_path, "paw-b", "lease-b")
