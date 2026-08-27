from __future__ import annotations

import argparse
import json
import sys

from .social import FacebookCapability, InstagramCapability, ThreadsCapability


def _emit(receipt) -> int:
    payload = receipt.to_dict()
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0 if payload.get("ok") else 2


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="AgentOS social capability boundary")
    parser.add_argument("platform", choices=["threads", "facebook", "instagram"])
    parser.add_argument("operation", choices=["identity", "read", "replies", "publish", "reply"])
    parser.add_argument("--credential")
    parser.add_argument("--thread-id")
    parser.add_argument("--object-id")
    parser.add_argument("--page-id")
    parser.add_argument("--ig-id")
    parser.add_argument("--title", default="")
    parser.add_argument("--text")
    parser.add_argument("--image-url")
    parser.add_argument("--image-path")
    parser.add_argument("--reply-to")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument(
        "--allow-write",
        action="store_true",
        help="Required for publish/reply. Prevents accidental social writes from read-only callers.",
    )
    args = parser.parse_args(argv)

    if args.platform == "threads":
        credential = args.credential or "threads/default"
        capability = ThreadsCapability(credential_ref=credential)
        if args.operation == "identity":
            return _emit(capability.identity_read())
        if args.operation == "read":
            if not args.thread_id:
                parser.error("--thread-id is required for Threads read")
            return _emit(capability.post_read(args.thread_id))
        if args.operation == "replies":
            if not args.thread_id:
                parser.error("--thread-id is required for Threads replies")
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
        if args.operation != "publish":
            parser.error("unsupported Threads operation")
        return _emit(capability.publish(args.text, image_url=args.image_url))

    if args.platform == "facebook":
        credential = args.credential or "facebook/default"
        capability = FacebookCapability(credential_ref=credential, page_id=args.page_id)
        if args.operation == "identity":
            return _emit(capability.identity_read())
        if args.operation not in {"publish", "reply"}:
            parser.error("Facebook v0.1 supports identity, publish, reply")
        if not args.allow_write:
            parser.error("--allow-write is required for publish/reply")
        if args.operation == "publish":
            if not args.image_path or not args.text:
                parser.error("--image-path and --text are required for Facebook publish")
            return _emit(capability.publish_photo(args.title, args.text, args.image_path))
        target = args.reply_to or args.object_id
        if not target or not args.text:
            parser.error("--reply-to/--object-id and --text are required for Facebook reply")
        return _emit(capability.comment(target, args.text))

    credential = args.credential or "instagram/default"
    capability = InstagramCapability(credential_ref=credential, page_id=args.page_id, ig_id=args.ig_id)
    if args.operation == "identity":
        return _emit(capability.identity_read())
    if args.operation not in {"publish", "reply"}:
        parser.error("Instagram v0.1 supports identity, publish, reply")
    if not args.allow_write:
        parser.error("--allow-write is required for publish/reply")
    if args.operation == "publish":
        if not args.image_url or not args.text:
            parser.error("--image-url and --text are required for Instagram publish")
        return _emit(capability.publish_image(args.title, args.text, args.image_url))
    target = args.reply_to or args.object_id
    if not target or not args.text:
        parser.error("--reply-to/--object-id and --text are required for Instagram reply")
    return _emit(capability.comment(target, args.text))


if __name__ == "__main__":
    sys.exit(main())
