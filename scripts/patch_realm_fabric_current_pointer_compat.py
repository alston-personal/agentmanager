#!/usr/bin/env python3
from pathlib import Path

path = Path('agentos_node/action_relay.py')
text = path.read_text(encoding='utf-8')
old = """            tmp_link = realm_root / f'.current-{source_commit}'
            tmp_link.unlink(missing_ok=True)
            tmp_link.symlink_to(release)
            tmp_link.replace(current)
            return {
                'ok': True,
                'source_commit': source_commit,
                'realm_id': realm_id,
                'release': str(release),
                'current': str(current),
"""
new = """            current_pointer_mode = 'symlink'
            if current.exists() and not current.is_symlink():
                # Preserve the legacy real directory. The systemd unit already
                # points at this exact versioned release, so replacing a live
                # directory just to normalize the pointer would be destructive.
                current_pointer_mode = 'legacy_directory_preserved'
            else:
                tmp_link = realm_root / f'.current-{source_commit}'
                tmp_link.unlink(missing_ok=True)
                tmp_link.symlink_to(release)
                tmp_link.replace(current)
            return {
                'ok': True,
                'source_commit': source_commit,
                'realm_id': realm_id,
                'release': str(release),
                'current': str(current),
                'current_pointer_mode': current_pointer_mode,
"""
if new in text:
    print('realm_fabric_current_pointer_compat=ALREADY_PRESENT')
    raise SystemExit(0)
if old not in text:
    raise SystemExit('legacy current-pointer block not found')
text = text.replace(old, new, 1)
compile(text, str(path), 'exec')
path.write_text(text, encoding='utf-8')
print('realm_fabric_current_pointer_compat=PASS')
