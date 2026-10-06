from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from agent_core.executor_job_contract import canonical_executor_job_request
from agentos_node import layoutlib_parity_provider as provider


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _release(tmp_path: Path) -> tuple[Path, bytes, bytes]:
    root = tmp_path / "layoutlib"
    release = root / "release" / provider.RELEASE
    release.mkdir(parents=True)
    html = b"<html><title>Layout Lab</title></html>\n"
    js = b"console.log('layoutlib');\n"
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
    return root, html, js


def test_layoutlib_parity_exact(monkeypatch, tmp_path: Path):
    root, html, js = _release(tmp_path)
    monkeypatch.setattr(
        provider.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(stdout="a" * 40 + "\n"),
    )
    def fake_fetch(url: str, *, timeout: float = 20.0):
        return (200, html if url.endswith("/layout-lab/") else js)
    monkeypatch.setattr(provider, "_fetch", fake_fetch)

    result = provider.inspect_layoutlib_production_parity(
        canonical_executor_job_request(provider.JOB_TYPE),
        repo_root=root,
    )
    assert result["verdict"] == "PASS"
    assert result["successful"] is True
    assert result["layoutlib_parity"] == "EXACT"
    assert result["layoutlib_matching_files"] == 2
    assert result["credential_exposed"] is False


def test_layoutlib_parity_mismatch_fails_closed(monkeypatch, tmp_path: Path):
    root, html, js = _release(tmp_path)
    monkeypatch.setattr(
        provider.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(stdout="b" * 40 + "\n"),
    )
    def fake_fetch(url: str, *, timeout: float = 20.0):
        return (200, html if url.endswith("/layout-lab/") else b"changed")
    monkeypatch.setattr(provider, "_fetch", fake_fetch)

    result = provider.inspect_layoutlib_production_parity(
        canonical_executor_job_request(provider.JOB_TYPE),
        repo_root=root,
    )
    assert result["verdict"] == "FAIL"
    assert result["successful"] is False
    assert result["classification"] == "LAYOUTLIB_PRODUCTION_PARITY_MISMATCH"
    assert result["layoutlib_parity"] == "MISMATCH"
