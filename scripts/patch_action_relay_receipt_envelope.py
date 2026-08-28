#!/usr/bin/env python3
from pathlib import Path

path = Path('agentos_node/action_relay.py')
text = path.read_text(encoding='utf-8')
marker = 'governed_receipt_reserved_fields_v1'
if marker in text:
    print('receipt_envelope_patch=ALREADY_PRESENT')
    raise SystemExit(0)

old = '            result = ACTIONS[action](params)\n            receipt = {"schema": RECEIPT_SCHEMA,"capsule_id": capsule_id,"action": action,"started_at": started,"completed_at": _now(),"executor_user": os.environ.get("USER") or str(os.getuid()),**result}\n'
new = '''            result = ACTIONS[action](params)\n            # governed_receipt_reserved_fields_v1: the relay owns receipt identity.\n            # Capability results may carry their own schema/metadata but must never\n            # overwrite the governance envelope used for validation and audit.\n            receipt = {\n                "schema": RECEIPT_SCHEMA,\n                "capsule_id": capsule_id,\n                "action": action,\n                "started_at": started,\n                "completed_at": _now(),\n                "executor_user": os.environ.get("USER") or str(os.getuid()),\n            }\n            reserved = {"schema", "capsule_id", "action", "started_at", "completed_at", "executor_user"}\n            for key, value in result.items():\n                receipt[("result_" + key) if key in reserved else key] = value\n'''
if old not in text:
    raise SystemExit('receipt assembly anchor not found')
text = text.replace(old, new, 1)
compile(text, str(path), 'exec')
path.write_text(text, encoding='utf-8')
print('receipt_envelope_patch=PASS')
