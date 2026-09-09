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
    args = parser.parse_args()
    try:
        print(repair(Path(args.path)))
    except Exception as exc:
        print(f"realm_fabric_store=REPAIR_REJECTED error={type(exc).__name__}:{exc}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
