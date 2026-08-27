from __future__ import annotations

import argparse
import json
from typing import Any

from agentos_node.social_capability import SocialCapability


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agentos-social")
    parser.add_argument("platform", choices=("threads", "facebook", "instagram"))
    parser.add_argument("operation", choices=("identity", "publish", "reply"))
    parser.add_argument("--credential", required=True, help="executor-local credential reference, never a token")
    parser.add_argument("--text")
    parser.add_argument("--title")
    parser.add_argument("--image-url")
    parser.add_argument("--image-path")
    parser.add_argument("--reply-to")
    parser.add_argument("--page-id")
    parser.add_argument("--ig-id")
    parser.add_argument("--allow-write", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    request: dict[str, Any] = {
        "text": args.text,
        "title": args.title,
        "image_url": args.image_url,
        "image_path": args.image_path,
        "reply_to": args.reply_to,
        "page_id": args.page_id,
        "ig_id": args.ig_id,
        "allow_write": args.allow_write,
    }
    receipt = SocialCapability().execute(args.platform, args.operation, args.credential, request)
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
    return 0 if receipt.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
