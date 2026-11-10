from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

from agent_core.employee_runtime import EmployeeRuntime
from agent_core.governed_execution import resolve_product_work_intent_ref


AUTHORITY_SCHEMA = "agentos.execution-authority/v1"
DEFAULT_AUTHORITY = Path(__file__).resolve().parents[1] / "governance" / "execution-authority.json"
DEFAULT_CACHE_ROOT = Path("/home/ubuntu/agent-data/product-work-intent-cache")
GIT_BIN = "/usr/bin/git"


def _load_registry(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema") != AUTHORITY_SCHEMA:
        raise ValueError("product_work_intent_authority_invalid")
    return value


def _run_git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [GIT_BIN, "-c", f"safe.directory={repo}", "-C", str(repo), *args],
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )


def _git_ok(repo: Path, *args: str, code: str) -> str:
    proc = _run_git(repo, *args)
    if proc.returncode:
        raise RuntimeError(code)
    return proc.stdout.strip()


def _ensure_bare_cache(
    project_id: str,
    project: dict[str, Any],
    *,
    cache_root: Path,
) -> tuple[Path, str]:
    repository = str(project.get("repository") or "").strip()
    source = project.get("request_source") or {}
    source_ref = str(source.get("source_ref") or "").strip()
    cache_ref = str(source.get("cache_ref") or "").strip()
    configured_root = Path(str(source.get("repo_root") or "")).expanduser()
    expected_root = (cache_root / f"{project_id}.git").resolve()
    if configured_root.resolve() != expected_root:
        raise RuntimeError("product_work_intent_cache_root_mismatch")
    if source_ref not in (project.get("allowed_source_refs") or []):
        raise RuntimeError("product_work_intent_source_ref_not_allowed")
    if not repository or not source_ref or not cache_ref.startswith("refs/agentos/"):
        raise RuntimeError("product_work_intent_source_invalid")

    expected_root.parent.mkdir(parents=True, exist_ok=True)
    expected_remote = f"https://github.com/{repository}.git"
    if not expected_root.exists():
        init = subprocess.run(
            [GIT_BIN, "init", "--bare", str(expected_root)],
            text=True,
            capture_output=True,
            check=False,
            timeout=30,
        )
        if init.returncode:
            raise RuntimeError("product_work_intent_cache_init_failed")
        add = _run_git(expected_root, "remote", "add", "origin", expected_remote)
        if add.returncode:
            raise RuntimeError("product_work_intent_cache_remote_failed")
    if _git_ok(expected_root, "rev-parse", "--is-bare-repository", code="product_work_intent_cache_invalid") != "true":
        raise RuntimeError("product_work_intent_cache_not_bare")
    remote = _git_ok(expected_root, "remote", "get-url", "origin", code="product_work_intent_cache_remote_unavailable")
    if remote.rstrip("/") not in {expected_remote, expected_remote.removesuffix(".git")}:
        raise RuntimeError("product_work_intent_cache_remote_mismatch")

    refspec = f"+refs/heads/{source_ref}:{cache_ref}"
    fetch = _run_git(expected_root, "fetch", "--no-tags", "--prune", "origin", refspec)
    if fetch.returncode:
        raise RuntimeError("product_work_intent_fetch_failed")
    _git_ok(expected_root, "rev-parse", cache_ref, code="product_work_intent_cache_ref_missing")
    return expected_root, cache_ref


def reconcile_once(
    *,
    runtime_root: str | Path,
    cache_root: str | Path = DEFAULT_CACHE_ROOT,
    authority_path: str | Path = DEFAULT_AUTHORITY,
) -> dict[str, Any]:
    authority = Path(authority_path).expanduser().resolve()
    cache = Path(cache_root).expanduser().resolve()
    registry = _load_registry(authority)
    projects = registry.get("projects") or {}
    runtime = EmployeeRuntime(Path(runtime_root).expanduser().resolve())
    results: list[dict[str, Any]] = []

    for project_id in sorted(projects):
        project = projects[project_id]
        if not isinstance(project, dict):
            continue
        binding = project.get("employee_binding")
        if not isinstance(binding, dict):
            continue
        employee_id = str(binding.get("employee_id") or "").strip()
        assignment_id = str(binding.get("assignment_id") or "").strip()
        if not employee_id or not assignment_id:
            raise RuntimeError("product_work_intent_binding_invalid")

        _ensure_bare_cache(project_id, project, cache_root=cache)
        ref = resolve_product_work_intent_ref(project_id, authority_path=authority)
        assignment = runtime.get_assignment(assignment_id)
        if assignment.employee_id != employee_id:
            raise RuntimeError("product_work_intent_assignment_employee_mismatch")
        changed = assignment.work_intent_ref != ref
        if changed:
            assignment = runtime.set_work_intent_ref(assignment_id, ref)
        results.append(
            {
                "project_id": project_id,
                "employee_id": employee_id,
                "assignment_id": assignment_id,
                "changed": changed,
                "work_intent_ref": assignment.work_intent_ref,
            }
        )

    return {
        "schema": "agentos.product-work-intent-reconcile-receipt/v1",
        "status": "completed",
        "project_count": len(results),
        "results": results,
        "credential_exposed": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-root", required=True)
    parser.add_argument("--cache-root", default=str(DEFAULT_CACHE_ROOT))
    parser.add_argument("--authority", default=str(DEFAULT_AUTHORITY))
    parser.add_argument("--once", action="store_true", required=True)
    args = parser.parse_args(argv)
    receipt = reconcile_once(
        runtime_root=args.runtime_root,
        cache_root=args.cache_root,
        authority_path=args.authority,
    )
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
