from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')


def _validate_snapshot(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get('schema') != 'agentos.realm-fabric/v0.1':
        raise RuntimeError('realm_fabric_repair_first_snapshot_invalid')
    realm_id = str(value.get('realm_id') or '').strip()
    if not realm_id:
        raise RuntimeError('realm_fabric_repair_realm_missing')
    for field in ('invites', 'join_requests', 'nodes', 'tasks', 'receipts'):
        if not isinstance(value.get(field), dict):
            raise RuntimeError(f'realm_fabric_repair_field_invalid:{field}')
    return value


def repair_truncated_tail(
    fabric_path: Path,
    *,
    expected_file_sha256: str,
    expected_prefix_sha256: str,
    backup_dir: Path,
) -> dict[str, Any]:
    fabric_path = Path(fabric_path).expanduser().resolve()
    backup_dir = Path(backup_dir).expanduser().resolve()
    lock_path = fabric_path.with_suffix(fabric_path.suffix + '.lock')
    fabric_path.parent.mkdir(parents=True, exist_ok=True)

    with lock_path.open('a+', encoding='utf-8') as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            original = fabric_path.read_bytes()
            observed_file_sha = _sha256_bytes(original)
            if observed_file_sha != expected_file_sha256:
                raise RuntimeError('realm_fabric_repair_file_sha_mismatch')

            try:
                text = original.decode('utf-8')
            except UnicodeDecodeError as exc:
                raise RuntimeError('realm_fabric_repair_not_utf8') from exc

            try:
                json.loads(text)
            except json.JSONDecodeError:
                pass
            else:
                raise RuntimeError('realm_fabric_repair_store_already_valid')

            decoder = json.JSONDecoder()
            try:
                first, end = decoder.raw_decode(text, 0)
            except json.JSONDecodeError as exc:
                raise RuntimeError('realm_fabric_repair_no_complete_prefix') from exc
            first = _validate_snapshot(first)
            prefix_text = text[:end]
            prefix_bytes = prefix_text.encode('utf-8')
            observed_prefix_sha = _sha256_bytes(prefix_bytes)
            if observed_prefix_sha != expected_prefix_sha256:
                raise RuntimeError('realm_fabric_repair_prefix_sha_mismatch')

            tail = text[end:]
            stripped = tail.lstrip()
            if not stripped:
                raise RuntimeError('realm_fabric_repair_no_truncated_tail')

            # If the remainder itself contains one complete JSON value, this is
            # not the narrowly approved truncated-tail case. Refuse rather than
            # choosing between multiple valid snapshots here.
            try:
                second, second_end = decoder.raw_decode(stripped, 0)
            except json.JSONDecodeError:
                second = None
                second_end = 0
            if second is not None and not stripped[second_end:].strip():
                raise RuntimeError('realm_fabric_repair_complete_second_snapshot_refused')

            backup_dir.mkdir(parents=True, exist_ok=True)
            backup_path = backup_dir / f'fabric.json.corrupt-{_utc_stamp()}-{observed_file_sha[:12]}'
            if backup_path.exists():
                raise RuntimeError('realm_fabric_repair_backup_collision')
            with backup_path.open('xb') as handle:
                handle.write(original)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(backup_path, 0o600)

            canonical = prefix_bytes + b'\n'
            fd, tmp_name = tempfile.mkstemp(
                prefix=fabric_path.name + '.repair.',
                suffix='.tmp',
                dir=str(fabric_path.parent),
            )
            tmp = Path(tmp_name)
            try:
                with os.fdopen(fd, 'wb') as handle:
                    handle.write(canonical)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.chmod(tmp, 0o640)
                os.replace(tmp, fabric_path)
                dir_fd = os.open(fabric_path.parent, os.O_RDONLY)
                try:
                    os.fsync(dir_fd)
                finally:
                    os.close(dir_fd)
            finally:
                if tmp.exists():
                    tmp.unlink()

            repaired = json.loads(fabric_path.read_text(encoding='utf-8'))
            _validate_snapshot(repaired)
            return {
                'schema': 'agentos.realm-fabric-repair/v1',
                'ok': True,
                'realm_id': first['realm_id'],
                'original_sha256': observed_file_sha,
                'restored_snapshot_sha256': observed_prefix_sha,
                'tail_bytes_quarantined': len(original) - len(prefix_bytes),
                'backup_path': str(backup_path),
                'credential_exposed': False,
            }
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog='repair-realm-fabric-truncated-tail')
    parser.add_argument('--fabric', type=Path, required=True)
    parser.add_argument('--expected-file-sha256', required=True)
    parser.add_argument('--expected-prefix-sha256', required=True)
    parser.add_argument('--backup-dir', type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = repair_truncated_tail(
        args.fabric,
        expected_file_sha256=args.expected_file_sha256,
        expected_prefix_sha256=args.expected_prefix_sha256,
        backup_dir=args.backup_dir,
    )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
