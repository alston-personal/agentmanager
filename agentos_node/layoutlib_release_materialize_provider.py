"""Bounded immutable LayoutLib release materializer for Oracle.

This provider never mutates a product working checkout. It clones the fixed
alston-personal/layoutlib repository into a temporary directory, verifies the
canonical v0.7.9 manifest and file hashes, then publishes an immutable snapshot
under /home/ubuntu/agent-data/releases/layoutlib/v0.7.9/<commit>/.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Any, Mapping

from agent_core.executor_job_contract import validate_executor_job
from agentos_node.executor_job_adapter import DEFAULT_PROVIDERS, ExecutorJobProviderRegistry

JOB_TYPE = "layoutlib.release.materialize"
PROVIDER_ID = "layoutlib-release-materialize-v1"
EXECUTOR_CLASS = "layoutlib-release-materializer"
EXPECTED_HOME = Path("/home/ubuntu")
DATA_ROOT = EXPECTED_HOME / "agent-data"
RELEASE = "v0.7.9"
SOURCE_REPOSITORY = "alston-personal/layoutlib"
RELEASE_ROOT = DATA_ROOT / "releases/layoutlib" / RELEASE
CURRENT_FILE = RELEASE_ROOT / "current.json"


def _failure(classification: str, *, executor_available: bool = True,
             routable: bool = True, authorized: bool = True) -> dict[str, Any]:
    return {
        "verdict": "FAIL",
        "classification": classification,
        "install_receipt_ok": False,
        "layoutlib_release": RELEASE,
        "executor_available": executor_available,
        "routable": routable,
        "authorized": authorized,
        "successful": False,
        "credential_exposed": False,
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verify_release(repo: Path) -> tuple[str, int]:
    release = repo / "release" / RELEASE
    manifest_path = release / "manifest.json"
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise ValueError("manifest_missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries = manifest.get("files")
    if manifest.get("release") != RELEASE or not isinstance(entries, list) or not entries:
        raise ValueError("manifest_invalid")
    for item in entries:
        if not isinstance(item, dict):
            raise ValueError("manifest_invalid")
        rel = str(item.get("destination") or "")
        expected = str(item.get("sha256") or "")
        if not rel.startswith(f"release/{RELEASE}/") or len(expected) != 64:
            raise ValueError("manifest_invalid")
        path = repo / rel
        if not path.is_file() or path.is_symlink() or _sha256(path) != expected:
            raise ValueError("release_hash_mismatch")
    return str(manifest.get("release")), len(entries)


def run_layoutlib_release_materialize(
    request: Mapping[str, Any],
    *,
    release_root: str | Path = RELEASE_ROOT,
) -> dict[str, Any]:
    spec = validate_executor_job(request)
    if spec.job_type != JOB_TYPE or spec.executor_class != EXECUTOR_CLASS:
        return _failure(
            "LAYOUTLIB_RELEASE_MATERIALIZE_CONTRACT_MISMATCH",
            executor_available=False,
            routable=False,
            authorized=False,
        )

    if Path.home() != EXPECTED_HOME or os.environ.get("USER") not in (None, "", "ubuntu"):
        return _failure(
            "LAYOUTLIB_RELEASE_UBUNTU_IDENTITY_MISMATCH",
            executor_available=False,
            routable=False,
            authorized=False,
        )
    if not DATA_ROOT.is_dir():
        return _failure(
            "LAYOUTLIB_RELEASE_AGENT_DATA_ROOT_UNAVAILABLE",
            executor_available=False,
            routable=False,
            authorized=False,
        )

    root = Path(release_root)
    root.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="agentos-layoutlib-release-") as td:
        checkout = Path(td) / "layoutlib"
        try:
            proc = subprocess.run(
                ["/usr/bin/gh", "repo", "clone", SOURCE_REPOSITORY, str(checkout), "--", "--depth=1"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=120,
                check=False,
                env={
                    "HOME": str(EXPECTED_HOME),
                    "USER": "ubuntu",
                    "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
                },
            )
        except subprocess.TimeoutExpired:
            return _failure("LAYOUTLIB_RELEASE_CLONE_TIMEOUT")
        except OSError:
            return _failure("LAYOUTLIB_RELEASE_CLONE_LAUNCH_ERROR")

        if proc.returncode != 0:
            text = ((proc.stdout or "") + "\n" + (proc.stderr or "")).casefold()
            if any(token in text for token in ("auth", "login", "credential", "permission denied")):
                return _failure("LAYOUTLIB_RELEASE_SOURCE_AUTH_REQUIRED", authorized=False)
            return _failure("LAYOUTLIB_RELEASE_CLONE_FAILED")

        try:
            head = subprocess.run(
                ["/usr/bin/git", "-C", str(checkout), "rev-parse", "HEAD"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=15,
                check=True,
            ).stdout.strip()
        except Exception:
            return _failure("LAYOUTLIB_RELEASE_HEAD_UNAVAILABLE")
        if len(head) != 40 or any(ch not in "0123456789abcdef" for ch in head):
            return _failure("LAYOUTLIB_RELEASE_HEAD_INVALID")

        try:
            _, count = _verify_release(checkout)
        except json.JSONDecodeError:
            return _failure("LAYOUTLIB_RELEASE_MANIFEST_INVALID")
        except ValueError as exc:
            mapping = {
                "manifest_missing": "LAYOUTLIB_RELEASE_MANIFEST_MISSING",
                "manifest_invalid": "LAYOUTLIB_RELEASE_MANIFEST_INVALID",
                "release_hash_mismatch": "LAYOUTLIB_RELEASE_HASH_MISMATCH",
            }
            return _failure(mapping.get(str(exc), "LAYOUTLIB_RELEASE_VERIFY_FAILED"))

        destination = root / head
        if destination.exists():
            try:
                _, existing_count = _verify_release(destination)
            except Exception:
                return _failure("LAYOUTLIB_RELEASE_EXISTING_SNAPSHOT_INVALID")
            if existing_count != count:
                return _failure("LAYOUTLIB_RELEASE_EXISTING_SNAPSHOT_INVALID")
        else:
            staging = root / (".staging-" + head)
            if staging.exists():
                shutil.rmtree(staging)
            staging.mkdir(mode=0o755)
            shutil.copytree(checkout / "release", staging / "release", symlinks=False)
            _verify_release(staging)
            os.replace(staging, destination)

        current = {
            "schema": "layoutlib.release-materialization/v1",
            "repository": SOURCE_REPOSITORY,
            "release": RELEASE,
            "commit": head,
            "snapshot": str(destination),
            "manifest_files": count,
            "credential_exposed": False,
        }
        tmp = root / ".current.json.tmp"
        tmp.write_text(json.dumps(current, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        os.chmod(tmp, 0o644)
        os.replace(tmp, root / "current.json")

    return {
        "verdict": "PASS",
        "classification": "LAYOUTLIB_RELEASE_MATERIALIZED",
        "install_receipt_ok": True,
        "observed_head": head,
        "layoutlib_release": RELEASE,
        "layoutlib_manifest_files": count,
        "executor_available": True,
        "routable": True,
        "authorized": True,
        "successful": True,
        "credential_exposed": False,
    }


def register_layoutlib_release_materialize_provider(
    registry: ExecutorJobProviderRegistry = DEFAULT_PROVIDERS,
) -> bool:
    existing = registry.get(JOB_TYPE)
    if existing is not None:
        if existing.provider_id == PROVIDER_ID and existing.executor_class == EXECUTOR_CLASS:
            return True
        raise RuntimeError("LayoutLib release materialize provider already registered differently")
    registry.register(
        job_type=JOB_TYPE,
        provider_id=PROVIDER_ID,
        executor_class=EXECUTOR_CLASS,
        handler=run_layoutlib_release_materialize,
    )
    return True
