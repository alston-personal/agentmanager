#!/usr/bin/env python3
from pathlib import Path

p = Path('agent_core/resolve_facade.py')
s = p.read_text(encoding='utf-8')
if 'continuation index generation mismatch' in s:
    print('already_patched=YES')
    raise SystemExit(0)

s = s.replace('import os\n', 'import os\nimport time\n', 1)
needle = '''def _continuation_projection(raw: dict[str, Any] | None) -> dict[str, Any] | None:\n'''
helper = '''def _continuation_index_id(raw: dict[str, Any] | None) -> str | None:\n    if not raw:\n        return None\n    direct = str(raw.get("index_id") or "").strip()\n    canonical_ir = raw.get("canonical_ir") if isinstance(raw.get("canonical_ir"), dict) else raw\n    nested = str(canonical_ir.get("index_id") or "").strip()\n    if direct and nested and direct != nested:\n        raise ValueError("continuation index_id mismatch between envelope and canonical_ir")\n    return direct or nested or None\n\n\ndef _read_continuation_pair(project_dir: Path, *, attempts: int = 5) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:\n    execution_path = project_dir / "execution-head.json"\n    continuation_path = project_dir / "continuity" / "latest.json"\n    last = None\n    for attempt in range(max(1, attempts)):\n        execution_head = _read_json(execution_path)\n        raw_continuation = _read_json(continuation_path)\n        head_index = str((execution_head or {}).get("index_id") or "").strip()\n        continuation_index = _continuation_index_id(raw_continuation)\n        fenced = bool(head_index or continuation_index)\n        if not fenced:\n            return execution_head, raw_continuation\n        if execution_head is not None and raw_continuation is not None and head_index and head_index == continuation_index:\n            return execution_head, raw_continuation\n        last = {"execution_head_index_id": head_index or None, "continuation_index_id": continuation_index}\n        if attempt + 1 < max(1, attempts):\n            time.sleep(0.01)\n    raise ValueError(f"continuation index generation mismatch: {last}")\n\n\n'''
if needle not in s:
    raise SystemExit('continuation projection insertion point missing')
s = s.replace(needle, helper + needle, 1)
old = '''    execution_head = _read_json(project_dir / "execution-head.json")\n    if execution_head is not None and execution_head.get("schema") != "agentos.execution-head/v1":\n        raise ValueError("unsupported execution-head schema")\n    raw_continuation = _read_json(project_dir / "continuity" / "latest.json")\n'''
new = '''    execution_head, raw_continuation = _read_continuation_pair(project_dir)\n    if execution_head is not None and execution_head.get("schema") != "agentos.execution-head/v1":\n        raise ValueError("unsupported execution-head schema")\n'''
if old not in s:
    raise SystemExit('resolve read block missing')
s = s.replace(old, new, 1)
p.write_text(s, encoding='utf-8')
print('resolve_continuation_index_fence_patch=PASS')
