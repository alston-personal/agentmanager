#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import mmap
import re
from pathlib import Path
from typing import Any


TOKENS = (
    "PreInvocation",
    "injectSteps",
    "ephemeralMessage",
    "hooks.json",
    ".gemini/config",
    ".gemini/hooks",
    "customization root",
)
MAX_CONTEXTS_PER_TOKEN = 6
CONTEXT_RADIUS = 220


def _compact_ascii(value: bytes) -> str:
    text = "".join(chr(byte) if 32 <= byte < 127 else " " for byte in value)
    return re.sub(r"\s+", " ", text).strip()


def _scan_file(path: Path) -> dict[str, Any]:
    counts = {token: 0 for token in TOKENS}
    contexts: dict[str, list[str]] = {token: [] for token in TOKENS}
    if not path.is_file():
        return {"path": str(path), "exists": False, "counts": counts, "contexts": contexts}
    with path.open("rb") as handle:
        with mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ) as data:
            for token in TOKENS:
                needle = token.encode("ascii")
                cursor = 0
                while True:
                    offset = data.find(needle, cursor)
                    if offset < 0:
                        break
                    counts[token] += 1
                    if len(contexts[token]) < MAX_CONTEXTS_PER_TOKEN:
                        start = max(0, offset - CONTEXT_RADIUS)
                        end = min(len(data), offset + len(needle) + CONTEXT_RADIUS)
                        contexts[token].append(_compact_ascii(data[start:end]))
                    cursor = offset + len(needle)
    return {
        "path": str(path),
        "exists": True,
        "size": path.stat().st_size,
        "counts": counts,
        "contexts": contexts,
    }


def inspect(app_root: Path) -> dict[str, Any]:
    desktop_payload = app_root / "resources" / "app"
    payload_root = desktop_payload if (desktop_payload / "product.json").is_file() else app_root
    product_path = payload_root / "product.json"
    product: dict[str, Any] = {}
    if product_path.is_file():
        loaded = json.loads(product_path.read_text(encoding="utf-8-sig"))
        if isinstance(loaded, dict):
            product = {
                key: loaded.get(key)
                for key in (
                    "nameShort",
                    "applicationName",
                    "dataFolderName",
                    "version",
                    "commit",
                    "quality",
                )
            }
    targets = [payload_root / "out" / "jetskiAgent" / "main.js"]
    targets.extend(
        sorted(
            (payload_root / "extensions" / "antigravity" / "bin").glob("language_server*")
        )
    )
    files = [_scan_file(path) for path in targets]
    totals = {
        token: sum(int(item["counts"][token]) for item in files)
        for token in TOKENS
    }
    return {
        "schema": "agentos.antigravity-hook-runtime-contract/v1",
        "app_root": str(app_root),
        "layout": "desktop" if payload_root == desktop_payload else "server",
        "product": product,
        "tokens": totals,
        "files": files,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app-root", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(inspect(args.app_root), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

