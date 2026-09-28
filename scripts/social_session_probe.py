#!/usr/bin/env python3
from __future__ import annotations
import json
from agentos_node.macos_chrome_threads import inspect_threads_tabs

def main() -> int:
    result=inspect_threads_tabs()
    print(json.dumps(result,ensure_ascii=False))
    return 0
if __name__=='__main__':
    raise SystemExit(main())
