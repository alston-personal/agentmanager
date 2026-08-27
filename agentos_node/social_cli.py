from __future__ import annotations

import argparse
import json
import sys

from .social import ThreadsCapability


def _emit(receipt) -> int:
    payload = receipt.to_dict()
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0 if payload.get("ok") else 2


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="AgentOS social capability boundary")
    parser.add_argument("platform", choices=["threads"])
    parser.add_argument("operation", choices=["identity", "read", "replies", "publish", "reply"])
    parser.add_argument("--credential", default="threads/default")
    parser.add_argument("--thread-id")
    parser.add_argument("--text")
    parser.add_argument("--image-url")
    parser.add_argument("--reply-to")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument(
        "--allow-write",
        action="store_true",
        help="Required for publish/reply. Prevents accidental social writes from read-only callers.",
    )
    args = parser.parse_args(argv)

    capability = ThreadsCapability(credential_ref=args.credential)
    if args.operation == "identity":
        return _emit(capability.identity_read())
    if args.operation == "read":
        if not args.thread_id:
            parser.error("--thread-id is required for read")
        return _emit(capability.post_read(args.thread_id))
    if args.operation == "replies":
        if not args.thread_id:
            parser.error("--thread-id is required for replies")
        return _emit(capability.replies_read(args.thread_id, limit=args.limit))

    if not args.allow_write:
        parser.error("--allow-write is required for publish/reply")
    if not args.text:
        parser.error("--text is required for publish/reply")
    if args.operation == "reply":
        target = args.reply_to or args.thread_id
        if not target:
            parser.error("--reply-to or --thread-id is required for reply")
        return _emit(capability.publish(args.text, image_url=args.image_url, reply_to_id=target))
    return _emit(capability.publish(args.text, image_url=args.image_url))


if __name__ == "__main__":
    sys.exit(main())
