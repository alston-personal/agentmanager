#!/usr/bin/env python3
import argparse
import csv
import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


SYSTEM_ROOT = Path("/home/dqa03/system")
REDMINE_DB_CONTAINER = "system-redmine_db"
REDMINE_DB_NAME = "redmine"
REDMINE_DB_ROOT_PASSWORD = "70703897"

RICH_ROOT = SYSTEM_ROOT / "redmine_app" / "redmine_system" / "rich" / "rich_files" / "rich_files"
RICH_BKP_ROOT = SYSTEM_ROOT / "redmine_app" / "redmine_system" / "bkp" / "rich_files" / "rich_files"
ATTACHMENTS_ROOT = SYSTEM_ROOT / "redmine_app" / "files"


@dataclass
class MissingFile:
    table: str
    record_id: int
    expected_path: Path
    backup_path: Path | None
    sibling_source_path: Path | None
    filename: str


def run_mysql(query: str) -> list[list[str]]:
    cmd = [
        "docker",
        "exec",
        REDMINE_DB_CONTAINER,
        "mysql",
        f"-uroot",
        f"-p{REDMINE_DB_ROOT_PASSWORD}",
        "-D",
        REDMINE_DB_NAME,
        "--default-character-set=utf8mb4",
        "-N",
        "-e",
        query,
    ]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    rows: list[list[str]] = []
    for line in result.stdout.splitlines():
        rows.append(line.split("\t"))
    return rows


def id_partition(record_id: int) -> Path:
    padded = f"{record_id:09d}"
    return Path(padded[:3]) / padded[3:6] / padded[6:9]


def iter_missing_rich() -> Iterable[MissingFile]:
    rows = run_mysql(
        "SELECT id, rich_file_file_name FROM rich_rich_files ORDER BY id"
    )
    for row in rows:
        record_id = int(row[0])
        filename = row[1]
        expected = RICH_ROOT / id_partition(record_id) / "original" / filename
        if expected.exists():
            continue
        sibling_source = None
        if expected.parent.is_dir():
            siblings = [path for path in expected.parent.iterdir() if path.is_file()]
            colon_variant = expected.parent / filename.replace(":", "_")
            if colon_variant.exists():
                sibling_source = colon_variant
            elif len(siblings) == 1:
                sibling_source = siblings[0]
        backup = RICH_BKP_ROOT / id_partition(record_id) / "original" / filename
        yield MissingFile(
            table="rich_rich_files",
            record_id=record_id,
            expected_path=expected,
            backup_path=backup if backup.exists() else None,
            sibling_source_path=sibling_source,
            filename=filename,
        )


def iter_missing_attachments() -> Iterable[MissingFile]:
    rows = run_mysql(
        "SELECT id, COALESCE(disk_directory,''), disk_filename, filename FROM attachments ORDER BY id"
    )
    for row in rows:
        record_id = int(row[0])
        disk_directory, disk_filename, filename = row[1], row[2], row[3]
        rel_path = Path(disk_directory) / disk_filename if disk_directory else Path(disk_filename)
        expected = ATTACHMENTS_ROOT / rel_path
        if expected.exists():
            continue
        yield MissingFile(
            table="attachments",
            record_id=record_id,
            expected_path=expected,
            backup_path=None,
            sibling_source_path=None,
            filename=filename,
        )


def restore_missing(files: list[MissingFile]) -> list[MissingFile]:
    restored: list[MissingFile] = []
    for item in files:
        source = None
        if item.backup_path and item.backup_path.exists():
            source = item.backup_path
        elif item.sibling_source_path and item.sibling_source_path.exists():
            source = item.sibling_source_path
        if not source:
            continue
        item.expected_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, item.expected_path)
        restored.append(item)
    return restored


def build_report(missing: list[MissingFile], restored: list[MissingFile]) -> dict:
    by_table: dict[str, dict[str, int]] = {}
    for name in ["rich_rich_files", "attachments"]:
        subset = [item for item in missing if item.table == name]
        by_table[name] = {
            "missing": len(subset),
            "restorable_from_backup": sum(1 for item in subset if item.backup_path),
            "restorable_from_sibling": sum(1 for item in subset if item.sibling_source_path),
            "restored": sum(1 for item in restored if item.table == name),
        }
    return {
        "system_root": str(SYSTEM_ROOT),
        "rich_root": str(RICH_ROOT),
        "attachments_root": str(ATTACHMENTS_ROOT),
        "summary": by_table,
        "missing_samples": [
            {
                "table": item.table,
                "record_id": item.record_id,
                "filename": item.filename,
                "expected_path": str(item.expected_path),
                "backup_path": str(item.backup_path) if item.backup_path else None,
                "sibling_source_path": str(item.sibling_source_path) if item.sibling_source_path else None,
            }
            for item in missing[:20]
        ],
    }


def write_csv(path: Path, missing: list[MissingFile]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["table", "record_id", "filename", "expected_path", "backup_path", "sibling_source_path"])
        for item in missing:
            writer.writerow(
                [
                    item.table,
                    item.record_id,
                    item.filename,
                    str(item.expected_path),
                    str(item.backup_path) if item.backup_path else "",
                    str(item.sibling_source_path) if item.sibling_source_path else "",
                ]
            )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit Redmine attachment and rich file consistency without stopping the live service."
    )
    parser.add_argument(
        "--restore",
        action="store_true",
        help="Copy back only missing rich files that exist in the local bkp tree.",
    )
    parser.add_argument(
        "--report-json",
        type=Path,
        default=Path("tmp/redmine_asset_audit_report.json"),
        help="Where to write the JSON summary report.",
    )
    parser.add_argument(
        "--report-csv",
        type=Path,
        default=Path("tmp/redmine_asset_missing.csv"),
        help="Where to write the CSV list of missing files.",
    )
    args = parser.parse_args()

    missing = list(iter_missing_rich()) + list(iter_missing_attachments())
    restored: list[MissingFile] = []
    if args.restore:
        restored = restore_missing(missing)

    report = build_report(missing, restored)
    args.report_json.parent.mkdir(parents=True, exist_ok=True)
    args.report_json.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_csv(args.report_csv, missing)

    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
