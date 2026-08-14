import glob
import pathlib

for p in glob.glob('/home/ubuntu/agent-data/projects/*/STATUS.md'):
    path = pathlib.Path(p)
    p_name = path.parent.name
    try:
        content = path.read_text(encoding='utf-8', errors='ignore')
    except Exception:
        continue
    last_status = ''
    last_updated = ''
    latest_log = ''
    for line in content.splitlines():
        if '| **Last Status** |' in line:
            parts = line.split('|')
            if len(parts) >= 4:
                last_status = parts[2].strip()
        elif '| **Last Updated** |' in line:
            parts = line.split('|')
            if len(parts) >= 4:
                last_updated = parts[2].strip()
        elif line.strip().startswith('-') and not latest_log:
            latest_log = line.strip()
    print(f'[{p_name}] | {last_status} | {last_updated} | {latest_log}')
