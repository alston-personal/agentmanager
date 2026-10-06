"""Bounded LayoutLib production promoter.

Publishes the fixed immutable LayoutLib v0.7.9 snapshot into the fixed Studio
production static directory. No caller-supplied path, repository, ref, URL,
command, or service mutation is accepted.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Mapping

from agent_core.executor_job_contract import validate_executor_job
from agentos_node.executor_job_adapter import DEFAULT_PROVIDERS, ExecutorJobProviderRegistry

JOB_TYPE = "layoutlib.production.promote"
PROVIDER_ID = "layoutlib-production-promote-v1"
EXECUTOR_CLASS = "layoutlib-production-promoter"
RELEASE = "v0.7.9"
MATERIALIZED_ROOT = Path("/home/ubuntu/agent-data/releases/layoutlib") / RELEASE
CURRENT_FILE = MATERIALIZED_ROOT / "current.json"
PRODUCTION_TARGET = Path("/home/ubuntu/zeus-writer/website/dist/layout-lab")
BACKUP_ROOT = Path("/home/ubuntu/agent-data/runtime/backups/layoutlib-production")
HTML_SOURCE = "layoutlab_v0_5.html"
HTML_TARGET = "index.html"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _failure(classification: str, **extra: Any) -> dict[str, Any]:
    return {
        "verdict": "FAIL",
        "classification": classification,
        "executor_available": True,
        "routable": True,
        "authorized": True,
        "successful": False,
        "credential_exposed": False,
        **extra,
    }


def _resolve_materialized_root(
    current_file: Path = CURRENT_FILE,
    materialized_root: Path = MATERIALIZED_ROOT,
) -> tuple[Path, str] | None:
    if not current_file.is_file() or current_file.is_symlink():
        return None
    try:
        data = json.loads(current_file.read_text(encoding="utf-8"))
    except Exception:
        return None
    commit = str(data.get("commit") or "")
    snapshot = str(data.get("snapshot") or "")
    if (
        data.get("schema") != "layoutlib.release-materialization/v1"
        or data.get("release") != RELEASE
        or len(commit) != 40
        or any(ch not in "0123456789abcdef" for ch in commit)
    ):
        return None
    expected = materialized_root / commit
    if snapshot != str(expected):
        return None
    return expected, commit


def _manifest(root: Path) -> tuple[list[dict[str, str]], str]:
    path = root / "release" / RELEASE / "manifest.json"
    if not path.is_file() or path.is_symlink():
        raise ValueError("manifest_missing")
    data = json.loads(path.read_text(encoding="utf-8"))
    entries = data.get("files")
    if data.get("release") != RELEASE or not isinstance(entries, list) or len(entries) != 7:
        raise ValueError("manifest_invalid")
    normalized: list[dict[str, str]] = []
    for item in entries:
        if not isinstance(item, dict):
            raise ValueError("manifest_invalid")
        rel = str(item.get("destination") or "")
        expected = str(item.get("sha256") or "")
        if not rel.startswith(f"release/{RELEASE}/") or len(expected) != 64:
            raise ValueError("manifest_invalid")
        src = root / rel
        if src.is_symlink() or not src.is_file() or _sha256(src) != expected:
            raise ValueError("hash_mismatch")
        normalized.append({"rel": rel, "sha256": expected})
    return normalized, str(data.get("source_commit") or "")


def run_layoutlib_production_promote(
    request: Mapping[str, Any],
    *,
    target: str | Path = PRODUCTION_TARGET,
    backup_root: str | Path = BACKUP_ROOT,
    current_file: str | Path = CURRENT_FILE,
    materialized_root: str | Path = MATERIALIZED_ROOT,
) -> dict[str, Any]:
    spec = validate_executor_job(request)
    if spec.job_type != JOB_TYPE or spec.executor_class != EXECUTOR_CLASS:
        return _failure(
            "LAYOUTLIB_PRODUCTION_PROMOTE_CONTRACT_MISMATCH",
            executor_available=False,
            routable=False,
            authorized=False,
        )

    resolved = _resolve_materialized_root(Path(current_file), Path(materialized_root))
    if resolved is None:
        return _failure("LAYOUTLIB_PRODUCTION_PROMOTE_RELEASE_UNAVAILABLE", layoutlib_release=RELEASE)
    source_root, source_commit = resolved

    try:
        entries, _historical_source = _manifest(source_root)
    except json.JSONDecodeError:
        return _failure("LAYOUTLIB_PRODUCTION_PROMOTE_MANIFEST_INVALID", layoutlib_release=RELEASE)
    except ValueError as exc:
        mapping = {
            "manifest_missing": "LAYOUTLIB_PRODUCTION_PROMOTE_MANIFEST_MISSING",
            "manifest_invalid": "LAYOUTLIB_PRODUCTION_PROMOTE_MANIFEST_INVALID",
            "hash_mismatch": "LAYOUTLIB_PRODUCTION_PROMOTE_SOURCE_CORRUPT",
        }
        return _failure(mapping.get(str(exc), "LAYOUTLIB_PRODUCTION_PROMOTE_SOURCE_INVALID"), layoutlib_release=RELEASE)

    dest = Path(target)
    parent = dest.parent
    if dest.is_symlink() or not parent.is_dir():
        return _failure("LAYOUTLIB_PRODUCTION_TARGET_INVALID", layoutlib_release=RELEASE)
    if dest.exists() and not dest.is_dir():
        return _failure("LAYOUTLIB_PRODUCTION_TARGET_INVALID", layoutlib_release=RELEASE)

    backups = Path(backup_root)
    backups.mkdir(parents=True, exist_ok=True)

    stage = Path(tempfile.mkdtemp(prefix=".layout-lab-promote-", dir=str(parent)))
    rollback = backups / ("before-" + source_commit)
    promoted = 0

    try:
        if dest.exists():
            shutil.copytree(dest, stage, dirs_exist_ok=True, symlinks=True)

        release_dir = source_root / "release" / RELEASE
        for item in entries:
            src = source_root / item["rel"]
            name = Path(item["rel"]).name
            out = stage / (HTML_TARGET if name == HTML_SOURCE else name)
            if out.exists() and out.is_symlink():
                return _failure("LAYOUTLIB_PRODUCTION_TARGET_SYMLINK", layoutlib_release=RELEASE)
            shutil.copy2(src, out)
            os.chmod(out, 0o644)
            if _sha256(out) != item["sha256"]:
                return _failure("LAYOUTLIB_PRODUCTION_STAGE_VERIFY_FAILED", layoutlib_release=RELEASE)
            promoted += 1

        if promoted != 7:
            return _failure("LAYOUTLIB_PRODUCTION_STAGE_INCOMPLETE", layoutlib_release=RELEASE)

        if rollback.exists():
            shutil.rmtree(rollback)
        if dest.exists():
            os.replace(dest, rollback)
        try:
            os.replace(stage, dest)
        except Exception:
            if rollback.exists() and not dest.exists():
                os.replace(rollback, dest)
            raise

        for item in entries:
            name = Path(item["rel"]).name
            out = dest / (HTML_TARGET if name == HTML_SOURCE else name)
            if not out.is_file() or out.is_symlink() or _sha256(out) != item["sha256"]:
                if dest.exists():
                    failed = parent / ".layout-lab-failed"
                    if failed.exists():
                        shutil.rmtree(failed)
                    os.replace(dest, failed)
                if rollback.exists():
                    os.replace(rollback, dest)
                return _failure("LAYOUTLIB_PRODUCTION_POSTSWAP_VERIFY_FAILED", layoutlib_release=RELEASE)

        return {
            "verdict": "PASS",
            "classification": "LAYOUTLIB_PRODUCTION_PROMOTED",
            "layoutlib_release": RELEASE,
            "observed_head": source_commit,
            "layoutlib_manifest_files": len(entries),
            "layoutlib_promoted_files": promoted,
            "layoutlib_rollback_retained": rollback.exists(),
            "executor_available": True,
            "routable": True,
            "authorized": True,
            "successful": True,
            "credential_exposed": False,
        }
    except Exception:
        return _failure("LAYOUTLIB_PRODUCTION_PROMOTE_ERROR", layoutlib_release=RELEASE)
    finally:
        if stage.exists():
            shutil.rmtree(stage, ignore_errors=True)


def register_layoutlib_production_promote_provider(
    registry: ExecutorJobProviderRegistry = DEFAULT_PROVIDERS,
) -> bool:
    existing = registry.get(JOB_TYPE)
    if existing is not None:
        if existing.provider_id == PROVIDER_ID and existing.executor_class == EXECUTOR_CLASS:
            return True
        raise RuntimeError("LayoutLib production promote provider already registered differently")
    registry.register(
        job_type=JOB_TYPE,
        provider_id=PROVIDER_ID,
        executor_class=EXECUTOR_CLASS,
        handler=run_layoutlib_production_promote,
    )
    return True
