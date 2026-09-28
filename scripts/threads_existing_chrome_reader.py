#!/usr/bin/env python3
from __future__ import annotations
import argparse, json
from agentos_node.macos_chrome_threads import inspect_threads_tabs, read_visible_threads_messages

def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument('--read',action='store_true')
    ap.add_argument('--max-chars',type=int,default=30000)
    args=ap.parse_args()
    result=read_visible_threads_messages(args.max_chars) if args.read else inspect_threads_tabs()
    print(json.dumps(result,ensure_ascii=False))
    return 0
if __name__=='__main__':
    raise SystemExit(main())
