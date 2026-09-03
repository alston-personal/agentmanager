"""ONE-owned Experience artifact persistence for issue #117.

Repository JSON is only a seed/provenance carrier. Runtime discovery and hydration
must read the accepted set from the AgentOS data layer so Experience is external to
an individual executor/session and is not silently coupled to a checkout.
"""
from __future__ import annotations

import fcntl
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Iterator
from contextlib import contextmanager

from agent_core.experience import ExperienceQuery, discover_experience, hydrate_experience, validate_experience

SET_SCHEMA = "agentos.experience-set/v0"
REGRESSION_SCHEMA = "agentos.experience-regression/v1"
PROMOTION_RECEIPT_SCHEMA = "agentos.experience-regression-promotion-receipt/v1"
ISSUE117_EXPERIENCE_ID = "core.experience-regression-ceiling-aware.v1"


def _data_root() -> Path:
    return Path(os.environ.get("AGENT_DATA_ROOT", os.environ.get("AGENTOS_DATA_ROOT", "/home/ubuntu/agent-data"))).expanduser()


def experience_path(project_id: str, *, data_root: Path | None = None) -> Path:
    project_id = str(project_id or "").strip()
    if not project_id or "/" in project_id or "\\" in project_id or project_id in {".", ".."}:
        raise ValueError("invalid project_id")
    root = data_root or _data_root()
    return root / "experience" / project_id / "accepted.json"


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _atomic_write(path: Path, value: dict[str, Any]) -> None:
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(_canonical_bytes(value))
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp, 0o640)
        os.replace(tmp, path)
        dir_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    finally:
        if tmp.exists():
            tmp.unlink()


def digest_set(value: dict[str, Any]) -> str:
    return "sha256:" + sha256(_canonical_bytes(value)).hexdigest()


def validate_set(value: dict[str, Any], *, project_id: str | None = None) -> dict[str, Any]:
    if value.get("schema") != SET_SCHEMA:
        raise ValueError("unsupported experience set schema")
    actual = str(value.get("project_id") or "").strip()
    if not actual:
        raise ValueError("experience set project_id is required")
    if project_id is not None and actual != project_id:
        raise ValueError("experience set project mismatch")
    artifacts = value.get("artifacts")
    if not isinstance(artifacts, list):
        raise ValueError("experience set artifacts must be a list")
    seen: set[str] = set()
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            raise ValueError("experience artifact must be an object")
        validate_experience(artifact)
        if artifact["project_id"] != actual:
            raise ValueError("experience artifact project mismatch")
        experience_id = artifact["experience_id"]
        if experience_id in seen:
            raise ValueError(f"duplicate experience_id: {experience_id}")
        seen.add(experience_id)
    return value


@contextmanager
def _lock(path: Path) -> Iterator[None]:
    lock = path.with_suffix(path.suffix + ".lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    if lock.is_symlink():
        raise ValueError("experience lock path must not be a symlink")
    with lock.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def read_experience_set(project_id: str, *, data_root: Path | None = None) -> dict[str, Any]:
    path = experience_path(project_id, data_root=data_root)
    if path.is_symlink():
        raise ValueError("experience store path must not be a symlink")
    if not path.is_file():
        raise FileNotFoundError(path)
    return validate_set(json.loads(path.read_text(encoding="utf-8")), project_id=project_id)


def seed_experience_set(seed_path: Path, *, data_root: Path | None = None) -> dict[str, Any]:
    seed_path = Path(seed_path)
    incoming = validate_set(json.loads(seed_path.read_text(encoding="utf-8")))
    project_id = incoming["project_id"]
    target = experience_path(project_id, data_root=data_root)
    incoming_digest = digest_set(incoming)
    target.parent.mkdir(parents=True, exist_ok=True)
    with _lock(target):
        if target.is_symlink():
            raise ValueError("experience store path must not be a symlink")
        if target.exists():
            current = validate_set(json.loads(target.read_text(encoding="utf-8")), project_id=project_id)
            current_digest = digest_set(current)
            if current_digest != incoming_digest:
                raise ValueError(
                    "ONE Experience already exists with a different digest; refusing implicit overwrite"
                )
            return {
                "schema": "agentos.experience-seed-receipt/v1",
                "ok": True,
                "seeded": False,
                "project_id": project_id,
                "digest": current_digest,
                "path": str(target),
                "credential_exposed": False,
            }
        _atomic_write(target, incoming)
    return {
        "schema": "agentos.experience-seed-receipt/v1",
        "ok": True,
        "seeded": True,
        "project_id": project_id,
        "digest": incoming_digest,
        "path": str(target),
        "credential_exposed": False,
    }


def _score(value: dict[str, Any], lane: str) -> float | None:
    score = value.get(lane)
    if not isinstance(score, dict):
        return None
    score = score.get("score")
    if not isinstance(score, dict):
        return None
    result = score.get("score")
    return float(result) if isinstance(result, (int, float)) and not isinstance(result, bool) else None


def _validate_regression_evidence(value: dict[str, Any]) -> None:
    if value.get("schema") != REGRESSION_SCHEMA:
        raise ValueError("unsupported regression evidence schema")
    if value.get("project_id") != "agentos-core":
        raise ValueError("regression evidence project mismatch")
    if value.get("executor") != "openai-codex-local":
        raise ValueError("regression evidence executor mismatch")
    checks = value.get("checks")
    if not isinstance(checks, dict):
        raise ValueError("regression evidence checks are required")
    required_checks = {
        "hydration_receipt_ok",
        "uplift_requirement_met",
        "no_regressed_dimensions",
        "critical_governance_pass",
    }
    if any(checks.get(key) is not True for key in required_checks):
        raise ValueError("regression evidence did not satisfy promotion checks")
    baseline = _score(value, "baseline")
    hydrated = _score(value, "hydrated")
    uplift = value.get("uplift")
    required_uplift = value.get("required_uplift")
    if baseline is None or hydrated is None or not isinstance(uplift, (int, float)) or not isinstance(required_uplift, (int, float)):
        raise ValueError("regression evidence scores are required")
    if value.get("verdict") != "PASS" or value.get("classification") != "EXPERIENCE_REGRESSION_PASS":
        raise ValueError("only a passing regression may be promoted")
    if value.get("credential_exposed") is not False:
        raise ValueError("regression evidence credential boundary failed")
    if hydrated < 0.83 or uplift + 1e-12 < required_uplift or hydrated < baseline:
        raise ValueError("regression evidence score requirements failed")
    if value.get("regressed_dimensions") != []:
        raise ValueError("regression evidence contains dimension regressions")
    if not isinstance(value.get("improved_dimensions"), list) or not value["improved_dimensions"]:
        raise ValueError("regression evidence must identify an improved dimension")


def _validate_authority_receipt(receipt: dict[str, Any], *, evidence_digest: str) -> None:
    if receipt.get("schema") != "agentos.experience-promotion-authority/v1":
        raise ValueError("unsupported promotion authority receipt")
    if receipt.get("project_id") != "agentos-core" or receipt.get("approved") is not True:
        raise ValueError("promotion authority is not approved for agentos-core")
    if receipt.get("evidence_sha256") != evidence_digest:
        raise ValueError("promotion authority receipt is not bound to this evidence")
    if not isinstance(receipt.get("approved_by"), str) or not receipt["approved_by"].strip():
        raise ValueError("promotion authority receipt requires approved_by")


def promote_issue117_regression_evidence(
    evidence_path: Path,
    authority_receipt: dict[str, Any],
    *,
    data_root: Path | None = None,
) -> dict[str, Any]:
    """Promote verified #117 evidence through the Core-owned Experience store.

    The caller must provide a human/Core authority receipt bound to the exact
    evidence digest. This deliberately cannot promote arbitrary conversation
    text or replace an existing Experience artifact.
    """
    root = (data_root or _data_root()).resolve()
    evidence_path = Path(evidence_path)
    if evidence_path.is_symlink() or not evidence_path.is_file():
        raise ValueError("regression evidence must be a regular file")
    evidence_root = root / "projects" / "agentos-core" / "evidence"
    try:
        evidence_path.resolve().relative_to(evidence_root.resolve())
    except ValueError:
        raise ValueError("regression evidence must be stored in the AgentOS data-layer evidence directory") from None
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    if not isinstance(evidence, dict):
        raise ValueError("regression evidence must be an object")
    _validate_regression_evidence(evidence)
    evidence_digest = "sha256:" + sha256(evidence_path.read_bytes()).hexdigest()
    _validate_authority_receipt(authority_receipt, evidence_digest=evidence_digest)

    target = experience_path("agentos-core", data_root=root)
    with _lock(target):
        current = read_experience_set("agentos-core", data_root=root)
        before_digest = digest_set(current)
        existing = next((item for item in current["artifacts"] if item["experience_id"] == ISSUE117_EXPERIENCE_ID), None)
        artifact = {
            "schema": "agentos.experience/v0",
            "experience_id": ISSUE117_EXPERIENCE_ID,
            "project_id": "agentos-core",
            "kind": "benchmark-pattern",
            "summary": "Experience regression must separately prove the Master Experience Floor and a ceiling-aware before/after uplift; a strong baseline may only have its remaining score headroom available.",
            "payload": {
                "benchmark_schema": REGRESSION_SCHEMA,
                "master_floor_score": 0.83,
                "uplift_rule": "min(0.34, 1.0 - baseline_score)",
                "baseline_score": _score(evidence, "baseline"),
                "hydrated_score": _score(evidence, "hydrated"),
                "uplift": evidence["uplift"],
                "required_uplift": evidence["required_uplift"],
                "improved_dimensions": list(evidence["improved_dimensions"]),
                "regressed_dimensions": [],
                "hydration_receipt_ok": True,
                "credential_exposed": False,
            },
            "provenance": {
                "sources": [f"evidence://agentos-core/{evidence_path.name}"],
                "accepted_evidence": [evidence_digest],
            },
            "authority": {"status": "accepted", "supersedes": [], "superseded_by": []},
            "validity": {
                "conditions": ["The regression contract and its Core-owned authority receipt remain valid."],
                "invalidated_by": [],
            },
            "realm_scope": ["oracle"],
            "capability_scope": ["agentos.core.develop", "agentos.one.resolve", "repository.merge"],
            "executor_scope": ["codex"],
        }
        validate_experience(artifact)
        if existing is not None:
            if existing != artifact:
                raise ValueError("issue117 Experience already exists with different promoted evidence")
            return {
                "schema": PROMOTION_RECEIPT_SCHEMA,
                "ok": True,
                "promoted": False,
                "project_id": "agentos-core",
                "experience_id": ISSUE117_EXPERIENCE_ID,
                "evidence_sha256": evidence_digest,
                "before_digest": before_digest,
                "after_digest": before_digest,
                "credential_exposed": False,
            }
        updated = dict(current)
        updated["artifacts"] = [*current["artifacts"], artifact]
        validate_set(updated, project_id="agentos-core")
        _atomic_write(target, updated)
        return {
            "schema": PROMOTION_RECEIPT_SCHEMA,
            "ok": True,
            "promoted": True,
            "project_id": "agentos-core",
            "experience_id": ISSUE117_EXPERIENCE_ID,
            "evidence_sha256": evidence_digest,
            "before_digest": before_digest,
            "after_digest": digest_set(updated),
            "credential_exposed": False,
        }


def discover_from_one(query: ExperienceQuery, *, data_root: Path | None = None) -> list[dict[str, Any]]:
    value = read_experience_set(query.project_id, data_root=data_root)
    return [dict(item) for item in discover_experience(value["artifacts"], query)]


def hydrate_from_one(
    *,
    project_id: str,
    active_goal: str,
    realm: str | None = None,
    capabilities: tuple[str, ...] = (),
    executor: str | None = None,
    limit: int = 20,
    data_root: Path | None = None,
) -> dict[str, Any]:
    artifacts = discover_from_one(
        ExperienceQuery(
            project_id=project_id,
            realm=realm,
            capabilities=capabilities,
            executor=executor,
            limit=limit,
        ),
        data_root=data_root,
    )
    projection = hydrate_experience(project_id=project_id, active_goal=active_goal, artifacts=artifacts).as_dict()
    projection["source"] = "ONE_EXPERIENCE"
    projection["credential_exposed"] = False
    return projection
