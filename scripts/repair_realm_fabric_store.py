#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any

SCHEMA = "agentos.realm-fabric/v0.1"


def _validate_snapshot(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("schema") != SCHEMA:
        raise ValueError("invalid Realm fabric snapshot schema")
    realm_id = str(value.get("realm_id") or "").strip()
    if not realm_id:
        raise ValueError("Realm fabric realm_id missing")
    for field in ("invites", "join_requests", "nodes", "tasks", "receipts"):
        if not isinstance(value.get(field, {}), dict):
            raise ValueError(f"invalid Realm fabric field: {field}")
    return value


def _decode_all(text: str) -> tuple[list[dict[str, Any]], bool]:
    decoder = json.JSONDecoder()
    idx = 0
    values: list[dict[str, Any]] = []
    used_nul_padding = False
    length = len(text)
    while idx < length:
        while idx < length and (text[idx].isspace() or text[idx] == "\x00"):
            used_nul_padding = used_nul_padding or text[idx] == "\x00"
            idx += 1
        if idx >= length:
            break
        value, end = decoder.raw_decode(text, idx)
        values.append(_validate_snapshot(value))
        idx = end
    return values, used_nul_padding


def probe_truncated_tail(path: Path) -> dict[str, Any]:
    """Return sanitized structural evidence only; never return tail contents."""
    original = path.read_bytes()
    file_sha = hashlib.sha256(original).hexdigest()
    try:
        text = original.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("Realm fabric store is not UTF-8") from exc

    decoder = json.JSONDecoder()
    try:
        first, end = decoder.raw_decode(text, 0)
    except json.JSONDecodeError as exc:
        raise ValueError("Realm fabric has no complete prefix snapshot") from exc
    first = _validate_snapshot(first)
    prefix_bytes = text[:end].encode("utf-8")
    prefix_sha = hashlib.sha256(prefix_bytes).hexdigest()
    tail = text[end:]
    stripped = tail.lstrip()
    second_complete = False
    if stripped:
        try:
            _second, second_end = decoder.raw_decode(stripped, 0)
        except json.JSONDecodeError:
            pass
        else:
            second_complete = not stripped[second_end:].strip()

    return {
        "schema": "agentos.realm-fabric-tail-probe/v1",
        "realm_id": first["realm_id"],
        "file_sha256": file_sha,
        "complete_prefix_sha256": prefix_sha,
        "prefix_bytes": len(prefix_bytes),
        "tail_bytes": len(original) - len(prefix_bytes),
        "second_complete": second_complete,
        "credential_exposed": False,
    }


def repair(path: Path) -> str:
    if not path.exists():
        return "realm_fabric_store=ABSENT"
    original = path.read_bytes()
    digest = hashlib.sha256(original).hexdigest()
    text = original.decode("utf-8")
    try:
        single = json.loads(text)
    except json.JSONDecodeError:
        snapshots, used_nul_padding = _decode_all(text)
        if not snapshots:
            raise ValueError("Realm fabric corruption contains no valid snapshot")
        if len(snapshots) < 2 and not used_nul_padding:
            raise ValueError("Realm fabric corruption is not a safe concatenated/padded snapshot case")
        realm_ids = {snapshot.get("realm_id") for snapshot in snapshots}
        if len(realm_ids) != 1:
            raise ValueError("concatenated Realm snapshots disagree on realm_id")
        selected = snapshots[-1]
    else:
        _validate_snapshot(single)
        return f"realm_fabric_store=VALID sha256={digest}"

    backup = path.with_name(f"{path.name}.corrupt-{digest}.bak")
    if backup.exists():
        if backup.read_bytes() != original:
            raise ValueError("hash-bound Realm fabric backup collision")
    else:
        backup.write_bytes(original)
        os.chmod(backup, 0o640)

    payload = json.dumps(selected, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".repair-", suffix=".tmp", dir=str(path.parent), text=True)
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
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
        tmp.unlink(missing_ok=True)

    repaired = json.loads(path.read_text(encoding="utf-8"))
    _validate_snapshot(repaired)
    if repaired.get("realm_id") not in realm_ids:
        raise ValueError("Realm fabric repair verification failed")
    return f"realm_fabric_store=REPAIRED source_sha256={digest} snapshots={len(snapshots)} nul_padding={str(used_nul_padding).lower()} backup={backup}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Fail-closed historical Realm Fabric store repair")
    parser.add_argument("--path", required=True)
    parser.add_argument("--probe-truncated-tail", action="store_true")
    args = parser.parse_args()
    try:
        if args.probe_truncated_tail:
            print(json.dumps(probe_truncated_tail(Path(args.path)), sort_keys=True))
        else:
            print(repair(Path(args.path)))
    except Exception as exc:
        kind = "PROBE_REJECTED" if args.probe_truncated_tail else "REPAIR_REJECTED"
        print(f"realm_fabric_store={kind} error={type(exc).__name__}:{exc}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
