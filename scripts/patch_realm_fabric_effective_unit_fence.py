#!/usr/bin/env python3
from pathlib import Path

path = Path('agentos_node/action_relay.py')
text = path.read_text(encoding='utf-8')
marker = 'realm_fabric_effective_unit_fence_v1'
if marker in text:
    print('realm_fabric_effective_unit_fence=ALREADY_PRESENT')
    raise SystemExit(0)

anchor = """            reload_step = _run(['systemctl', '--user', 'daemon-reload'], cwd=Path.home(), timeout=15)
"""
insert = """            # realm_fabric_effective_unit_fence_v1
            # A historical drop-in can override the exact-release WorkingDirectory,
            # PYTHONPATH and ExecStart written above.  The fenced installer is the
            # only authority allowed to neutralize that generation override.  Keep
            # unrelated drop-ins (for example controller.env) intact.
            legacy_dropin = Path('/home/ubuntu/.config/systemd/user/agentos-realm-fabric.service.d/runtime-generation.conf')
            legacy_backup = Path('/home/ubuntu/agent-data/governance/legacy-systemd-dropins') / 'agentos-realm-fabric.runtime-generation.conf'
            if legacy_dropin.is_file():
                legacy_text = legacy_dropin.read_text(encoding='utf-8')
                required_markers = (
                    '/home/ubuntu/.local/share/agentos/realm-fabric/current',
                    'ExecStart=/usr/bin/python3 -m agent_core.realm_cli serve --host 127.0.0.1 --port 8780',
                )
                if not all(m in legacy_text for m in required_markers):
                    return {
                        'ok': False,
                        'stage': 'effective_unit_fence',
                        'error': 'unrecognized runtime-generation.conf; refusing mutation',
                        'source_commit': source_commit,
                        'steps': steps,
                    }
                legacy_backup.parent.mkdir(parents=True, exist_ok=True)
                if not legacy_backup.exists():
                    legacy_backup.write_text(legacy_text, encoding='utf-8')
                    _share(legacy_backup)
                legacy_dropin.unlink()
                steps.append({
                    'step': 'quarantine_legacy_runtime_generation_dropin',
                    'ok': True,
                    'source': str(legacy_dropin),
                    'backup': str(legacy_backup),
                })

            reload_step = _run(['systemctl', '--user', 'daemon-reload'], cwd=Path.home(), timeout=15)
"""
if anchor not in text:
    raise SystemExit('daemon reload anchor not found')
text = text.replace(anchor, insert, 1)

compile(text, str(path), 'exec')
path.write_text(text, encoding='utf-8')
print('realm_fabric_effective_unit_fence=PASS')
