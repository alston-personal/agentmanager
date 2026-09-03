"""ONE-owned Experience artifact persistence for issue #117.

Accepted Experience is external ONE data. Repository JSON is a governed
seed/provenance carrier. Schema migration is explicit and only permitted when the
installed legacy set byte-semantically matches a repository-approved legacy seed
and preserves the complete experience_id set.
"""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Iterator

from agent_core.experience import ExperienceQuery, discover_experience, hydrate_experience, validate_experience

SET_SCHEMA = "agentos.experience-set/v1"
LEGACY_SET_SCHEMA = "agentos.experience-set/v0"


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


def digest_set(value: dict[str, Any]) -> str:
    return "sha256:" + sha256(_canonical_bytes(value)).hexdigest()


def _artifact_ids(value: dict[str, Any]) -> tuple[str, ...]:
    artifacts = value.get("artifacts")
    if not isinstance(artifacts, list):
        raise ValueError("experience set artifacts must be a list")
    ids: list[str] = []
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            raise ValueError("experience artifact must be an object")
        experience_id = str(artifact.get("experience_id") or "").strip()
        if not experience_id:
            raise ValueError("experience artifact id is required")
        ids.append(experience_id)
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate experience_id")
    return tuple(ids)


def validate_set(value: dict[str, Any], *, project_id: str | None = None) -> dict[str, Any]:
    if value.get("schema") != SET_SCHEMA:
        raise ValueError("unsupported experience set schema")
    actual = str(value.get("project_id") or "").strip()
    if not actual:
        raise ValueError("experience set project_id is required")
    if project_id is not None and actual != project_id:
        raise ValueError("experience set project mismatch")
    if value.get("projection_only") is not True:
        raise ValueError("experience set must declare projection_only=true")
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


def _validate_known_legacy(value: dict[str, Any], *, project_id: str) -> dict[str, Any]:
    if value.get("schema") != LEGACY_SET_SCHEMA:
        raise ValueError("known migration source must be Experience set v0")
    if str(value.get("project_id") or "").strip() != project_id:
        raise ValueError("legacy Experience project mismatch")
    if value.get("projection_only") is not True:
        raise ValueError("legacy Experience set must be projection-only")
    _artifact_ids(value)
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


def _atomic_write(target: Path, value: dict[str, Any]) -> None:
    fd, tmp_name = tempfile.mkstemp(prefix=target.name + ".", suffix=".tmp", dir=str(target.parent))
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(_canonical_bytes(value))
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp, 0o640)
        os.replace(tmp, target)
        dir_fd = os.open(target.parent, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    finally:
        if tmp.exists():
            tmp.unlink()


def read_experience_set(project_id: str, *, data_root: Path | None = None) -> dict[str, Any]:
    path = experience_path(project_id, data_root=data_root)
    if path.is_symlink():
        raise ValueError("experience store path must not be a symlink")
    if not path.is_file():
        raise FileNotFoundError(path)
    return validate_set(json.loads(path.read_text(encoding="utf-8")), project_id=project_id)


def seed_experience_set(
    seed_path: Path,
    *,
    data_root: Path | None = None,
    migrate_from: Path | None = None,
) -> dict[str, Any]:
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
            raw_current = json.loads(target.read_text(encoding="utf-8"))
            if raw_current.get("schema") == SET_SCHEMA:
                current = validate_set(raw_current, project_id=project_id)
                current_digest = digest_set(current)
                if current_digest != incoming_digest:
                    raise ValueError("ONE Experience already exists with a different digest; refusing implicit overwrite")
                return {
                    "schema": "agentos.experience-seed-receipt/v1",
                    "ok": True,
                    "seeded": False,
                    "migrated": False,
                    "project_id": project_id,
                    "digest": current_digest,
                    "path": str(target),
                    "credential_exposed": False,
                }

            if migrate_from is None:
                raise ValueError("legacy ONE Experience requires an explicit known migration source")
            expected_path = Path(migrate_from)
            expected_legacy = _validate_known_legacy(
                json.loads(expected_path.read_text(encoding="utf-8")),
                project_id=project_id,
            )
            current_legacy = _validate_known_legacy(raw_current, project_id=project_id)
            current_digest = digest_set(current_legacy)
            expected_digest = digest_set(expected_legacy)
            if current_digest != expected_digest:
                raise ValueError("installed legacy Experience does not match approved migration source")
            if set(_artifact_ids(current_legacy)) != set(_artifact_ids(incoming)):
                raise ValueError("Experience migration would add/drop accepted experience IDs; refusing migration")

            backup = target.with_name(f"accepted.v0.{current_digest.split(':', 1)[1]}.json")
            if backup.is_symlink():
                raise ValueError("Experience migration backup path must not be a symlink")
            if backup.exists():
                backup_value = json.loads(backup.read_text(encoding="utf-8"))
                if digest_set(backup_value) != current_digest:
                    raise ValueError("Experience migration backup exists with unexpected content")
            else:
                _atomic_write(backup, current_legacy)
            _atomic_write(target, incoming)
            return {
                "schema": "agentos.experience-seed-receipt/v1",
                "ok": True,
                "seeded": True,
                "migrated": True,
                "project_id": project_id,
                "from_schema": LEGACY_SET_SCHEMA,
                "from_digest": current_digest,
                "digest": incoming_digest,
                "backup_path": str(backup),
                "path": str(target),
                "credential_exposed": False,
            }

        _atomic_write(target, incoming)

    return {
        "schema": "agentos.experience-seed-receipt/v1",
        "ok": True,
        "seeded": True,
        "migrated": False,
        "project_id": project_id,
        "digest": incoming_digest,
        "path": str(target),
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
