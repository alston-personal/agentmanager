from __future__ import annotations

import json
from pathlib import Path

import pytest

import agentos_node.product_work_intent_reconciler as reconciler
from agent_core.employee_runtime import EmployeeRuntime


REF = {
    "schema": "agentos.employee-work-intent-ref/v1",
    "product_id": "zeus-writer",
    "state_key": "current-work",
    "revision": 1,
    "digest": "sha256:" + "a" * 64,
}


def _registry(path: Path) -> Path:
    payload = {
        "schema": "agentos.execution-authority/v1",
        "projects": {
            "zeus-writer": {
                "repository": "alston-personal/zeus-writer",
                "request_path": ".agentos/execution-requests/draft-review.json",
                "allowed_source_refs": ["master"],
                "request_source": {
                    "repo_root": str(path.parent / "cache" / "zeus-writer.git"),
                    "source_ref": "master",
                    "cache_ref": "refs/agentos/master",
                },
                "employee_binding": {
                    "employee_id": "zeus-writer",
                    "assignment_id": "zeus-writer-continuation-v1",
                },
            }
        },
        "capabilities": {},
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _runtime(path: Path) -> EmployeeRuntime:
    runtime = EmployeeRuntime(path)
    runtime.create_employee("zeus-writer", "Zeus Writer")
    runtime.create_assignment(
        "zeus-writer-continuation-v1",
        "zeus-writer",
        "continue governed writing work",
    )
    return runtime


def test_reconcile_binds_changed_ref_once_then_is_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runtime_root = tmp_path / "runtime"
    runtime = _runtime(runtime_root)
    authority = _registry(tmp_path / "authority.json")
    cache_root = tmp_path / "cache"

    fetches = []
    monkeypatch.setattr(
        reconciler,
        "_ensure_bare_cache",
        lambda project_id, project, cache_root: fetches.append((project_id, cache_root)) or (cache_root / "zeus-writer.git", "refs/agentos/master"),
    )
    monkeypatch.setattr(
        reconciler,
        "resolve_product_work_intent_ref",
        lambda project_id, authority_path: dict(REF),
    )

    first = reconciler.reconcile_once(
        runtime_root=runtime_root,
        cache_root=cache_root,
        authority_path=authority,
    )
    second = reconciler.reconcile_once(
        runtime_root=runtime_root,
        cache_root=cache_root,
        authority_path=authority,
    )

    assert first["results"][0]["changed"] is True
    assert second["results"][0]["changed"] is False
    assert runtime.get_assignment("zeus-writer-continuation-v1").work_intent_ref == REF
    assert len(fetches) == 2
    assert first["credential_exposed"] is False


def test_reconcile_refuses_assignment_employee_mismatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runtime_root = tmp_path / "runtime"
    runtime = EmployeeRuntime(runtime_root)
    runtime.create_employee("zeus-writer", "Zeus Writer")
    runtime.create_employee("other", "Other")
    runtime.create_assignment("zeus-writer-continuation-v1", "other", "wrong")
    authority = _registry(tmp_path / "authority.json")
    monkeypatch.setattr(reconciler, "_ensure_bare_cache", lambda *args, **kwargs: (tmp_path / "cache.git", "refs/agentos/master"))
    monkeypatch.setattr(reconciler, "resolve_product_work_intent_ref", lambda *args, **kwargs: dict(REF))

    with pytest.raises(RuntimeError, match="assignment_employee_mismatch"):
        reconciler.reconcile_once(
            runtime_root=runtime_root,
            cache_root=tmp_path / "cache",
            authority_path=authority,
        )


def test_service_is_periodic_bounded_and_has_no_generic_exec_authority() -> None:
    root = Path(__file__).resolve().parents[1]
    service = (root / ".agent" / "scripts" / "agentos-product-work-intent-reconciler.service").read_text(encoding="utf-8")
    timer = (root / ".agent" / "scripts" / "agentos-product-work-intent-reconciler.timer").read_text(encoding="utf-8")
    assert "product_work_intent_reconciler" in service
    assert "--once" in service
    assert "NoNewPrivileges=true" in service
    assert "ReadWritePaths=/home/ubuntu/agent-data/employee-runtime /home/ubuntu/agent-data/product-work-intent-cache" in service
    assert "OnUnitActiveSec=60s" in timer
    assert "shell.exec" not in service
    assert "argv" not in service
