#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from agent_core.realm_fabric import RealmFabricStore


def main() -> int:
    parser = argparse.ArgumentParser(description='Externalize Realm Fabric receipts into durable SQLite archive')
    parser.add_argument('--path', type=Path, default=None)
    args = parser.parse_args()

    store = RealmFabricStore(path=args.path)
    result = store.externalize_receipts()
    print(json.dumps(result, sort_keys=True, separators=(',', ':')))
    print('realm_receipt_externalization=PASS')
    print('realm_hot_receipt_count=' + str(result['hot_receipt_count']))
    print('realm_archive_receipt_count=' + str(result['archive_receipt_count']))
    print('realm_fabric_after_bytes=' + str(result['after_bytes']))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
