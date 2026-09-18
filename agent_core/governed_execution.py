from __future__ import annotations

import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


AUTHORITY_SCHEMA = "agentos.execution-authority/v1"
REQUEST_SCHEMA = "agentos.execution-request/v1"
RECEIPT_SCHEMA = "agentos.execution-receipt/v1"
WORK_REF_SCHEMA = "agentos.employee-work-intent-ref/v1"
ZEUS_WORK_SCHEMA = "zeus.writer-work-intent/v1"
SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
REQUEST_KEYS = {
    "schema",
    "request_id",
    "project_id",
    "repository",
    "source_ref",
    "source_sha",
    "capability",
    "environment",
    "parameters",
    "replay_policy",
    "expected_result",
}
DEFAULT_AUTHORITY_PATH = Path(__file__).resolve().parent.parent / "governance" / "execution-authority.json"
GIT_BIN = "/usr/bin/git"


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _fail(code: str) -> None:
    raise RuntimeError(code)


def _load_json(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        _fail("governed_execution_json_object_required")
    return value


def _canonical_json(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        dict(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _run_git(repo_root: str | Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [GIT_BIN, "-c", f"safe.directory={Path(repo_root)}", "-C", str(repo_root), *args],
        text=True,
        capture_output=True,
        check=False,
        timeout=10,
    )


def _git_value(repo_root: str | Path, *args: str, error_code: str) -> str:
    proc = _run_git(repo_root, *args)
    if proc.returncode:
        _fail(error_code)
    return proc.stdout


def sanitize_remote(value: str) -> str:
    text = str(value or "").strip()
    if "://" in text:
        text = re.sub(r"(https?://)[^/@]+@", r"\1", text)
    return text


def _validate_parameter(value: Any, policy: Mapping[str, Any], field: str) -> None:
    kind = policy.get("type")
    if kind == "string":
        if not isinstance(value, str):
            _fail(f"governed_execution_parameter_{field}_type")
        allowed = policy.get("enum")
        if allowed is not None and value not in allowed:
            _fail(f"governed_execution_parameter_{field}_enum")
        pattern = policy.get("pattern")
        if pattern is not None and re.fullmatch(str(pattern), value) is None:
            _fail(f"governed_execution_parameter_{field}_pattern")
        return
    if kind == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            _fail(f"governed_execution_parameter_{field}_type")
        if value < int(policy.get("minimum", value)):
            _fail(f"governed_execution_parameter_{field}_minimum")
        return
    if kind == "sha256":
        if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
            _fail(f"governed_execution_parameter_{field}_sha256")
        return
    _fail("governed_execution_parameter_policy_invalid")


def validate_parameters(parameters: Any, policy: Any) -> dict[str, Any]:
    if not isinstance(parameters, dict) or not isinstance(policy, dict):
        _fail("governed_execution_parameters_invalid")
    if set(parameters) != set(policy):
        _fail("governed_execution_parameter_keys_mismatch")
    for field, rule in policy.items():
        if not isinstance(rule, dict):
            _fail("governed_execution_parameter_policy_invalid")
        _validate_parameter(parameters[field], rule, field)
    return dict(parameters)


def resolve_authority(
    request: Mapping[str, Any],
    registry: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    if set(request) != REQUEST_KEYS:
        _fail("governed_execution_request_keys_mismatch")
    if request.get("schema") != REQUEST_SCHEMA:
        _fail("governed_execution_request_schema_invalid")
    if request.get("expected_result") != RECEIPT_SCHEMA:
        _fail("governed_execution_receipt_schema_invalid")
    if not isinstance(request.get("request_id"), str) or not str(request["request_id"]).strip():
        _fail("governed_execution_request_id_invalid")
    if SHA40_RE.fullmatch(str(request.get("source_sha") or "")) is None:
        _fail("governed_execution_source_sha_invalid")
    if registry.get("schema") != AUTHORITY_SCHEMA:
        _fail("governed_execution_authority_schema_invalid")

    project = (registry.get("projects") or {}).get(request.get("project_id"))
    capability = (registry.get("capabilities") or {}).get(request.get("capability"))
    if not isinstance(project, dict) or not isinstance(capability, dict):
        _fail("governed_execution_authority_missing")
    if project.get("repository") != request.get("repository"):
        _fail("governed_execution_repository_mismatch")
    if request.get("source_ref") not in (project.get("allowed_source_refs") or []):
        _fail("governed_execution_source_ref_not_allowed")
    if capability.get("project_id") != request.get("project_id"):
        _fail("governed_execution_capability_project_mismatch")
    if capability.get("environment") != request.get("environment"):
        _fail("governed_execution_environment_mismatch")
    if capability.get("replay_policy") != request.get("replay_policy"):
        _fail("governed_execution_replay_policy_mismatch")
    validate_parameters(request.get("parameters"), capability.get("parameter_policy"))
    return dict(project), dict(capability)


def load_local_product_request(
    project_id: str,
    *,
    authority_path: str | Path = DEFAULT_AUTHORITY_PATH,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    registry = _load_json(authority_path)
    project = (registry.get("projects") or {}).get(project_id)
    if not isinstance(project, dict):
        _fail("governed_execution_project_not_allowed")
    source = project.get("request_source")
    if not isinstance(source, dict):
        _fail("governed_execution_request_source_missing")
    repo_root = str(source.get("repo_root") or "").strip()
    cache_ref = str(source.get("cache_ref") or "").strip()
    request_path = str(project.get("request_path") or "").strip()
    if (
        not repo_root
        or not cache_ref
        or not request_path
        or request_path.startswith("/")
        or ".." in Path(request_path).parts
    ):
        _fail("governed_execution_request_source_invalid")

    remote = sanitize_remote(
        _git_value(repo_root, "remote", "get-url", "origin", error_code="governed_execution_remote_unavailable")
    ).strip()
    expected_remote = f"https://github.com/{project['repository']}.git"
    if remote not in {expected_remote, expected_remote.removesuffix(".git")}:
        _fail("governed_execution_repository_identity_mismatch")

    raw = _git_show_bytes(repo_root, cache_ref, request_path)
    try:
        request = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        _fail("governed_execution_product_request_invalid")
    if not isinstance(request, dict):
        _fail("governed_execution_product_request_invalid")
    resolved_project, capability = resolve_authority(request, registry)
    if request.get("project_id") != project_id:
        _fail("governed_execution_project_identity_mismatch")
    return request, resolved_project, capability


def _git_show_bytes(repo_root: str | Path, source_sha: str, relative_path: str) -> bytes:
    if (
        not relative_path
        or relative_path.startswith("/")
        or ".." in Path(relative_path).parts
        or "\x00" in relative_path
    ):
        _fail("governed_execution_relative_path_invalid")
    proc = subprocess.run(
        [
            GIT_BIN,
            "-c",
            f"safe.directory={Path(repo_root)}",
            "-C",
            str(repo_root),
            "show",
            f"{source_sha}:{relative_path}",
        ],
        capture_output=True,
        check=False,
        timeout=10,
    )
    if proc.returncode:
        _fail("governed_execution_source_blob_missing")
    return bytes(proc.stdout)


def _validated_zeus_manifest(
    request: Mapping[str, Any],
    capability: Mapping[str, Any],
    expected_work_ref: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], str]:
    runtime = capability.get("runtime") or {}
    repo_root = str(runtime.get("repo_root") or "")
    manifest_path = str(runtime.get("work_intent_path") or "")
    if not repo_root or not manifest_path:
        _fail("zeus_review_runtime_authority_invalid")

    raw_manifest = _git_show_bytes(repo_root, str(request["source_sha"]), manifest_path)
    try:
        manifest = json.loads(raw_manifest.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        _fail("zeus_review_manifest_invalid")
    if not isinstance(manifest, dict) or manifest.get("schema") != ZEUS_WORK_SCHEMA:
        _fail("zeus_review_manifest_schema_invalid")

    ref = manifest.get("core_ref")
    selected = manifest.get("selected_work")
    if not isinstance(ref, dict) or not isinstance(selected, dict):
        _fail("zeus_review_manifest_shape_invalid")
    if expected_work_ref is not None and ref != dict(expected_work_ref):
        _fail("zeus_review_work_ref_mismatch")
    if ref.get("schema") != WORK_REF_SCHEMA:
        _fail("zeus_review_work_ref_schema_invalid")

    params = request["parameters"]
    if (
        ref.get("product_id") != "zeus-writer"
        or ref.get("state_key") != params.get("work_intent_state_key")
        or ref.get("revision") != params.get("work_intent_revision")
        or ref.get("digest") != params.get("work_intent_digest")
    ):
        _fail("zeus_review_request_work_ref_mismatch")

    digest = "sha256:" + hashlib.sha256(_canonical_json(selected)).hexdigest()
    if digest != ref.get("digest"):
        _fail("zeus_review_manifest_digest_mismatch")
    if selected.get("action") != "review_existing_draft":
        _fail("zeus_review_action_not_allowed")
    if selected.get("chapter") != params.get("chapter"):
        _fail("zeus_review_chapter_mismatch")
    if selected.get("mutation_allowed") is not False or selected.get("publish_allowed") is not False:
        _fail("zeus_review_mutation_boundary_invalid")
    return dict(ref), dict(selected), digest


def resolve_product_work_intent_ref(
    project_id: str,
    *,
    authority_path: str | Path = DEFAULT_AUTHORITY_PATH,
) -> dict[str, Any]:
    request, project, capability = load_local_product_request(project_id, authority_path=authority_path)
    source = project.get("request_source") or {}
    repo_root = str(source.get("repo_root") or "")
    cache_ref = str(source.get("cache_ref") or "")
    ancestry = _run_git(repo_root, "merge-base", "--is-ancestor", str(request["source_sha"]), cache_ref)
    if ancestry.returncode != 0:
        _fail("governed_execution_source_sha_not_in_release_lane")
    adapter = str(capability.get("adapter") or "")
    if adapter != "zeus_draft_review":
        _fail("governed_execution_work_intent_adapter_not_supported")
    ref, _, _ = _validated_zeus_manifest(request, capability)
    return ref


def _zeus_draft_review(
    request: Mapping[str, Any],
    capability: Mapping[str, Any],
    expected_work_ref: Mapping[str, Any],
) -> tuple[dict[str, Any], bool]:
    runtime = capability.get("runtime") or {}
    repo_root = str(runtime.get("repo_root") or "")
    allowed_prefix = str(runtime.get("allowed_draft_prefix") or "")
    if not repo_root or not allowed_prefix:
        _fail("zeus_review_runtime_authority_invalid")
    ref, selected, digest = _validated_zeus_manifest(
        request,
        capability,
        expected_work_ref,
    )
    params = request["parameters"]

    draft_path = str(selected.get("draft_path") or "")
    if (
        not draft_path.startswith(allowed_prefix)
        or draft_path.startswith("/")
        or ".." in Path(draft_path).parts
        or not draft_path.endswith(".md")
    ):
        _fail("zeus_review_draft_path_not_allowed")

    draft = _git_show_bytes(repo_root, str(request["source_sha"]), draft_path)
    try:
        text = draft.decode("utf-8")
    except UnicodeDecodeError:
        _fail("zeus_review_draft_encoding_invalid")
    first_line = text.splitlines()[0].strip() if text.splitlines() else ""
    expected_heading = f"# 第{params['chapter'][2:]}章"
    heading_matches = first_line.startswith(expected_heading)
    sections = sum(1 for line in text.splitlines() if line.startswith("## "))
    substantial = len(draft) >= 2000 and len(text.strip()) >= 1000 and sections >= 2

    evidence = {
        "source_sha": request["source_sha"],
        "work_intent_digest": digest,
        "work_intent_revision": ref.get("revision"),
        "project": selected.get("project"),
        "action": selected.get("action"),
        "chapter": selected.get("chapter"),
        "draft_path": draft_path,
        "draft_sha256": hashlib.sha256(draft).hexdigest(),
        "draft_bytes": len(draft),
        "draft_characters": len(text),
        "section_count": sections,
        "heading_matches_chapter": heading_matches,
        "substantial_existing_draft": substantial,
        "mutation_performed": False,
        "publish_performed": False,
        "credential_exposed": False,
    }
    return evidence, bool(heading_matches and substantial)


ADAPTERS = {
    "zeus_draft_review": _zeus_draft_review,
}


def execute_bound_work_intent(
    expected_work_ref: Mapping[str, Any],
    *,
    authority_path: str | Path = DEFAULT_AUTHORITY_PATH,
) -> dict[str, Any]:
    request, project, capability = load_local_product_request(
        str(expected_work_ref.get("product_id") or ""),
        authority_path=authority_path,
    )
    adapter = ADAPTERS.get(str(capability.get("adapter") or ""))
    if adapter is None:
        _fail("governed_execution_adapter_not_installed")

    receipt: dict[str, Any] = {
        "schema": RECEIPT_SCHEMA,
        "request_id": request["request_id"],
        "project_id": request["project_id"],
        "repository": request["repository"],
        "environment": request["environment"],
        "source_ref": request["source_ref"],
        "source_sha": request["source_sha"],
        "capability": request["capability"],
        "result_status": "failed",
        "evidence_level": "exact_source_read_only_product_review",
        "started_at": _now(),
        "completed_at": None,
        "evidence": {},
        "credential_exposed": False,
    }
    try:
        evidence, accepted = adapter(request, capability, expected_work_ref)
        receipt["evidence"] = evidence
        receipt["result_status"] = "success" if accepted else "mismatch"
    except RuntimeError as exc:
        receipt["error_code"] = str(exc)
    finally:
        receipt["completed_at"] = _now()
    return receipt
