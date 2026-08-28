#!/usr/bin/env python3
from pathlib import Path

path = Path('agentos_node/action_relay.py')
text = path.read_text(encoding='utf-8')
marker = 'realm_fabric_release_isolation_v1'
if marker in text:
    print('realm_fabric_release_isolation=ALREADY_PRESENT')
    raise SystemExit(0)

old_launcher = """            launcher.write_text(
                '#!/usr/bin/env bash\\nset -euo pipefail\\n'
                f'export PYTHONPATH={release}:\"${{PYTHONPATH:-}}\"\\n'
                'exec /usr/bin/python3 -m agent_core.realm_cli \"$@\"\\n',
                encoding='utf-8',
            )
"""
new_launcher = """            launcher.write_text(
                '#!/usr/bin/env bash\\nset -euo pipefail\\n'
                f'# realm_fabric_release_isolation_v1\\ncd {release}\\n'
                'export PYTHONNOUSERSITE=1\\n'
                f'export PYTHONPATH={release}:\"${{PYTHONPATH:-}}\"\\n'
                'exec /usr/bin/python3 -m agent_core.realm_cli \"$@\"\\n',
                encoding='utf-8',
            )
"""
if old_launcher not in text:
    raise SystemExit('launcher block not found')
text = text.replace(old_launcher, new_launcher, 1)

old_unit = """                '[Service]\\nType=simple\\n'
                f'Environment=AGENT_DATA_ROOT={data_root}\\n'
                f'ExecStart={launcher} serve --host 127.0.0.1 --port 8780\\n'
"""
new_unit = """                '[Service]\\nType=simple\\n'
                f'Environment=AGENT_DATA_ROOT={data_root}\\n'
                'Environment=PYTHONNOUSERSITE=1\\n'
                f'WorkingDirectory={release}\\n'
                f'ExecStart={launcher} serve --host 127.0.0.1 --port 8780\\n'
"""
if old_unit not in text:
    raise SystemExit('unit block not found')
text = text.replace(old_unit, new_unit, 1)

compile(text, str(path), 'exec')
path.write_text(text, encoding='utf-8')
print('realm_fabric_release_isolation=PASS')
