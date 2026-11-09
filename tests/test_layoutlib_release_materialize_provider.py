from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from agent_core.executor_job_contract import canonical_executor_job_request, validate_executor_job
from agentos_node import layoutlib_release_materialize_provider as provider


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _fake_release(checkout: Path) -> None:
    release = checkout / "release" / provider.RELEASE
    release.mkdir(parents=True, exist_ok=True)
    html = b"<html>canonical</html>\n"
    js = b"console.log('canonical');\n"
    (release / "layoutlab_v0_5.html").write_bytes(html)
    (release / "layoutlib-browser-v0.5.js").write_bytes(js)
    manifest = {
        "release": provider.RELEASE,
        "files": [
            {
                "destination": f"release/{provider.RELEASE}/layoutlab_v0_5.html",
                "sha256": _sha(html),
            },
            {
                "destination": f"release/{provider.RELEASE}/layoutlib-browser-v0.5.js",
                "sha256": _sha(js),
            },
        ],
    }
    (release / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def test_layoutlib_release_materialize_contract_is_fixed_and_mutating_but_bounded():
    req = canonical_executor_job_request(provider.JOB_TYPE)
    spec = validate_executor_job(req)
    assert spec.project_id == "layoutlib"
    assert spec.executor_class == "layoutlib-release-materializer"
    assert spec.workload_ref == "release://layoutlib/v0.7.9"
    assert spec.authority == "bounded-product-release-materialize"
    assert spec.read_only is False


def test_layoutlib_release_materialize_publishes_immutable_snapshot(monkeypatch, tmp_path: Path):
    data_root = tmp_path / "agent-data"
    data_root.mkdir()
    release_root = data_root / "releases/layoutlib" / provider.RELEASE

    monkeypatch.setattr(provider.Path, "home", classmethod(lambda cls: provider.EXPECTED_HOME))
    monkeypatch.setenv("USER", "ubuntu")

    def fake_run(argv, **kwargs):
        argv = list(argv)
        if argv[:4] == ["/usr/bin/gh", "repo", "clone", provider.SOURCE_REPOSITORY]:
            checkout = Path(argv[4])
            checkout.mkdir(parents=True)
            _fake_release(checkout)
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if argv[:4] == ["/usr/bin/git", "-C", argv[2], "fetch"]:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if argv[:4] == ["/usr/bin/git", "-C", argv[2], "checkout"]:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if argv[:4] == ["/usr/bin/git", "-C", argv[2], "rev-parse"]:
            return SimpleNamespace(returncode=0, stdout=provider.SOURCE_COMMIT + "\n", stderr="")
        raise AssertionError(argv)

    monkeypatch.setattr(provider.subprocess, "run", fake_run)

    result = provider.run_layoutlib_release_materialize(
        canonical_executor_job_request(provider.JOB_TYPE),
        release_root=release_root,
        data_root=data_root,
    )
    assert result["verdict"] == "PASS"
    assert result["successful"] is True
    assert result["install_receipt_ok"] is True
    assert result["observed_head"] == provider.SOURCE_COMMIT
    assert result["layoutlib_manifest_files"] == 2

    snapshot = release_root / provider.SOURCE_COMMIT
    assert (snapshot / "release" / provider.RELEASE / "manifest.json").is_file()
    current = json.loads((release_root / "current.json").read_text())
    assert current["commit"] == provider.SOURCE_COMMIT
    assert current["snapshot"] == str(snapshot)


def test_layoutlib_release_materialize_hash_mismatch_fails_closed(monkeypatch, tmp_path: Path):
    data_root = tmp_path / "agent-data"
    data_root.mkdir()
    release_root = data_root / "releases/layoutlib" / provider.RELEASE

    monkeypatch.setattr(provider.Path, "home", classmethod(lambda cls: provider.EXPECTED_HOME))
    monkeypatch.setenv("USER", "ubuntu")

    def fake_run(argv, **kwargs):
        argv = list(argv)
        if argv[:4] == ["/usr/bin/gh", "repo", "clone", provider.SOURCE_REPOSITORY]:
            checkout = Path(argv[4])
            checkout.mkdir(parents=True)
            _fake_release(checkout)
            (checkout / "release" / provider.RELEASE / "layoutlab_v0_5.html").write_text("tampered")
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if argv[:4] == ["/usr/bin/git", "-C", argv[2], "fetch"]:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if argv[:4] == ["/usr/bin/git", "-C", argv[2], "checkout"]:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if argv[:4] == ["/usr/bin/git", "-C", argv[2], "rev-parse"]:
            return SimpleNamespace(returncode=0, stdout=provider.SOURCE_COMMIT + "\n", stderr="")
        raise AssertionError(argv)

    monkeypatch.setattr(provider.subprocess, "run", fake_run)

    result = provider.run_layoutlib_release_materialize(
        canonical_executor_job_request(provider.JOB_TYPE),
        release_root=release_root,
        data_root=data_root,
    )
    assert result["successful"] is False
    assert result["classification"] == "LAYOUTLIB_RELEASE_HASH_MISMATCH"
    assert not (release_root / "current.json").exists()
