#!/usr/bin/env python3
"""Build a reproducible WoW AddOn ZIP only from explicitly locked local files.

This does not fetch repositories, install files, or assert in-game compatibility.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import zipfile
from pathlib import Path, PurePosixPath

SHA256 = re.compile(r"^[0-9a-f]{64}$")
ADDON = re.compile(r"^[A-Za-z0-9_]+$")
SOURCE = re.compile(r"^[A-Za-z0-9_./-]+$")
ZIP_TIME = (1980, 1, 1, 0, 0, 0)


class BundleError(ValueError):
    pass


def _relative(raw: object) -> str:
    if not isinstance(raw, str) or not raw or not SOURCE.fullmatch(raw):
        raise BundleError("invalid file path")
    path = PurePosixPath(raw)
    if path.is_absolute() or any(p in ("..", ".") for p in raw.split("/")) or str(path) != raw:
        raise BundleError("unsafe or noncanonical file path")
    return str(path)


def build_bundle(lock_file: Path, sources_root: Path, output: Path) -> dict:
    lock = json.loads(lock_file.read_text(encoding="utf-8"))
    if lock.get("schema") != "agentos.wow-suite-source-lock/v1":
        raise BundleError("unsupported source lock")
    entries = lock.get("files")
    if not isinstance(entries, list) or not entries:
        raise BundleError("source lock must contain files")
    sources_root = sources_root.resolve(strict=True)
    payloads: dict[str, bytes] = {}
    addons: dict[str, set[str]] = {}
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"addon", "path", "sha256"}:
            raise BundleError("invalid lock entry fields")
        addon = entry["addon"]
        if not isinstance(addon, str) or not ADDON.fullmatch(addon):
            raise BundleError("invalid addon folder name")
        path = _relative(entry["path"])
        digest = entry["sha256"]
        if not isinstance(digest, str) or not SHA256.fullmatch(digest):
            raise BundleError("invalid sha256")
        target = f"{addon}/{path}"
        if target in payloads:
            raise BundleError("duplicate output path")
        src = sources_root / addon / path
        resolved = src.resolve(strict=True)
        if not resolved.is_relative_to(sources_root) or not resolved.is_file():
            raise BundleError("source escapes locked directory")
        if resolved.is_symlink() or src.is_symlink():
            raise BundleError("symlink sources are forbidden")
        blob = resolved.read_bytes()
        if hashlib.sha256(blob).hexdigest() != digest:
            raise BundleError(f"SHA256 mismatch for {target}")
        if path.lower().endswith((".lua", ".toc", ".xml")):
            if b"\x00" in blob:
                raise BundleError("NUL in AddOn source")
        payloads[target] = blob
        addons.setdefault(addon, set()).add(path)
    for addon, files in addons.items():
        if f"{addon}.toc" not in files:
            raise BundleError(f"missing top-level TOC for {addon}")
    output.parent.mkdir(parents=True, exist_ok=True)
    meta = {
        "schema": "agentos.wow-suite-package-manifest/v1",
        "status": "source-verified-not-game-validated",
        "addon_folders": sorted(addons),
        "files": [{"path": name, "sha256": hashlib.sha256(payloads[name]).hexdigest()}
                  for name in sorted(payloads)],
    }
    payloads["WOW_SUITE_BUILD_MANIFEST.json"] = (
        json.dumps(meta, sort_keys=True, indent=2) + "\n").encode("utf-8")
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name, blob in sorted(payloads.items()):
            info = zipfile.ZipInfo(name, date_time=ZIP_TIME)
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, blob, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    output.write_bytes(data.getvalue())
    return {"output": str(output), "sha256": hashlib.sha256(data.getvalue()).hexdigest(),
            "file_count": len(meta["files"]), "addon_folders": sorted(addons),
            "status": "source-verified-not-game-validated"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", type=Path, required=True)
    parser.add_argument("--sources-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = build_bundle(args.lock, args.sources_root, args.output)
    except (BundleError, OSError, ValueError, KeyError) as exc:
        parser.exit(2, f"WoW bundle refused: {exc}\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
