"""Read a previously mirrored Mio Threads publish result without publishing.

Usage: python3 -m agentos_node.mio_receipt_read mio-post-<slug>
This is a local Oracle read-only entrypoint, not an exposed ChatGPT connector.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

KEY_PATTERN = re.compile(r"mio-post-[a-z0-9-]{1,72}\Z")


def read_result(post_key: str, root: Path | None = None) -> dict:
    if not KEY_PATTERN.fullmatch(post_key):
        raise ValueError("invalid post_key")
    root = root or Path(os.environ.get("AGENTOS_MIO_RECEIPT_DIR") or
                        "/home/ubuntu/.local/state/agentos/social/mio-publish-receipts")
    path = root / (post_key + ".json")
    # Refuse symlinks so an untrusted filename cannot redirect the read.
    if path.is_symlink():
        raise ValueError("receipt symlink forbidden")
    result = json.loads(path.read_text(encoding="utf-8"))
    if result.get("schema") != "agentos.mio-publish-result/v1" or result.get("post_key") != post_key:
        raise ValueError("receipt schema or key mismatch")
    return result


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: python3 -m agentos_node.mio_receipt_read mio-post-<slug>", file=sys.stderr)
        return 2
    try:
        row = read_result(argv[1])
    except FileNotFoundError:
        print(json.dumps({"post_key": argv[1], "state": "NOT_RECORDED"}))
        return 1
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"receipt_read_error={type(exc).__name__}", file=sys.stderr)
        return 2
    print(json.dumps(row, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
