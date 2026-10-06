from __future__ import annotations

import hashlib
import json
from pathlib import Path

from agent_core.executor_job_contract import canonical_executor_job_request, validate_executor_job
from agentos_node import layoutlib_production_promote_provider as provider


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _prepare_snapshot(root: Path, commit: str = "7b9c1487d19d5d7ab5f4b817a01aed2b1919b591"):
    materialized = root / "materialized"
    snapshot = materialized / commit
    release = snapshot / "release" / provider.RELEASE
    release.mkdir(parents=True)

    files = {
        "layoutlab_v0_5.html": b"<html>canonical-v079</html>\n",
        "layoutlib-browser-v0.5.js": b"browser\n",
        "layoutlib-spatial-semantics-v0.1.js": b"semantics\n",
        "layoutlib-editor-v0.7.js": b"editor\n",
        "layoutlab-editor-ui-v0.7.js": b"ui\n",
        "layoutlab-capability-bridge-v0.7.js": b"bridge\n",
        "layoutlab-v0.7-release-fix.js": b"fix\n",
    }
    entries = []
    for name, data in files.items():
        (release / name).write_bytes(data)
        entries.append({
            "destination": f"release/{provider.RELEASE}/{name}",
            "sha256": _sha(data),
        })
    (release / "manifest.json").write_text(json.dumps({
        "release": provider.RELEASE,
        "files": entries,
        "source_commit": "e8efc4ed7cbd41839f960373f79c5fb6a5f82375",
    }), encoding="utf-8")
    current = materialized / "current.json"
    current.write_text(json.dumps({
        "schema": "layoutlib.release-materialization/v1",
        "release": provider.RELEASE,
        "commit": commit,
        "snapshot": str(snapshot),
    }), encoding="utf-8")
    return materialized, current, snapshot, files


def test_layoutlib_production_promote_contract_is_fixed():
    req = canonical_executor_job_request(provider.JOB_TYPE)
    spec = validate_executor_job(req)
    assert spec.project_id == "layoutlib"
    assert spec.executor_class == "layoutlib-production-promoter"
    assert spec.workload_ref == "release://layoutlib/v0.7.9"
    assert spec.authority == "bounded-product-production-promote"
    assert spec.read_only is False


def test_layoutlib_production_promote_overwrites_only_canonical_assets(tmp_path: Path):
    materialized, current, _snapshot, files = _prepare_snapshot(tmp_path)
    target = tmp_path / "site" / "layout-lab"
    target.mkdir(parents=True)
    (target / "keep-me.txt").write_text("preserve", encoding="utf-8")
    (target / "index.html").write_text("old", encoding="utf-8")
    backup = tmp_path / "backups"

    result = provider.run_layoutlib_production_promote(
        canonical_executor_job_request(provider.JOB_TYPE),
        target=target,
        backup_root=backup,
        current_file=current,
        materialized_root=materialized,
    )
    assert result["verdict"] == "PASS"
    assert result["successful"] is True
    assert result["layoutlib_promoted_files"] == 7
    assert result["layoutlib_manifest_files"] == 7
    assert result["layoutlib_rollback_retained"] is True

    assert (target / "index.html").read_bytes() == files["layoutlab_v0_5.html"]
    for name, data in files.items():
        if name == "layoutlab_v0_5.html":
            continue
        assert (target / name).read_bytes() == data
    assert (target / "keep-me.txt").read_text(encoding="utf-8") == "preserve"


def test_layoutlib_production_promote_refuses_corrupt_source(tmp_path: Path):
    materialized, current, snapshot, _files = _prepare_snapshot(tmp_path)
    (snapshot / "release" / provider.RELEASE / "layoutlib-editor-v0.7.js").write_text("tampered")
    target = tmp_path / "site" / "layout-lab"
    target.mkdir(parents=True)
    (target / "index.html").write_text("old", encoding="utf-8")

    result = provider.run_layoutlib_production_promote(
        canonical_executor_job_request(provider.JOB_TYPE),
        target=target,
        backup_root=tmp_path / "backups",
        current_file=current,
        materialized_root=materialized,
    )
    assert result["successful"] is False
    assert result["classification"] == "LAYOUTLIB_PRODUCTION_PROMOTE_SOURCE_CORRUPT"
    assert (target / "index.html").read_text(encoding="utf-8") == "old"
