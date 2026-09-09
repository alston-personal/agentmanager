from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path


def _load_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "repair_realm_fabric_store.py"
    spec = importlib.util.spec_from_file_location("repair_realm_fabric_store", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _snapshot(realm_id: str, marker: str) -> dict:
    return {
        "schema": "agentos.realm-fabric/v0.1",
        "realm_id": realm_id,
        "invites": {},
        "join_requests": {},
        "nodes": {},
        "tasks": {},
        "receipts": {marker: {"ok": True}},
    }


def test_valid_store_is_noop(tmp_path: Path) -> None:
    module = _load_module()
    path = tmp_path / "fabric.json"
    payload = json.dumps(_snapshot("realm-alston", "one"), sort_keys=True) + "\n"
    path.write_text(payload, encoding="utf-8")
    before = path.read_bytes()
    result = module.repair(path)
    assert result.startswith("realm_fabric_store=VALID")
    assert path.read_bytes() == before
    assert list(tmp_path.glob("*.bak")) == []


def test_concatenated_valid_snapshots_keep_last_and_backup_original(tmp_path: Path) -> None:
    module = _load_module()
    path = tmp_path / "fabric.json"
    first = _snapshot("realm-alston", "old")
    last = _snapshot("realm-alston", "new")
    original = (json.dumps(first) + "\n" + json.dumps(last) + "\n").encode()
    path.write_bytes(original)
    digest = hashlib.sha256(original).hexdigest()
    result = module.repair(path)
    assert result.startswith("realm_fabric_store=REPAIRED")
    assert json.loads(path.read_text(encoding="utf-8")) == last
    backup = tmp_path / f"fabric.json.corrupt-{digest}.bak"
    assert backup.read_bytes() == original


def test_partial_or_garbage_corruption_is_rejected(tmp_path: Path) -> None:
    module = _load_module()
    path = tmp_path / "fabric.json"
    path.write_text(json.dumps(_snapshot("realm-alston", "one")) + "\n{", encoding="utf-8")
    before = path.read_bytes()
    try:
        module.repair(path)
    except Exception:
        pass
    else:
        raise AssertionError("expected fail-closed rejection")
    assert path.read_bytes() == before


def test_cross_realm_concatenation_is_rejected(tmp_path: Path) -> None:
    module = _load_module()
    path = tmp_path / "fabric.json"
    original = json.dumps(_snapshot("realm-a", "one")) + json.dumps(_snapshot("realm-b", "two"))
    path.write_text(original, encoding="utf-8")
    try:
        module.repair(path)
    except ValueError as exc:
        assert "realm_id" in str(exc)
    else:
        raise AssertionError("expected fail-closed realm mismatch")
