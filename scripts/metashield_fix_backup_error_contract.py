from pathlib import Path
import json

ROOT = Path('/home/ubuntu/metashield-protocol')
bg_path = ROOT / 'extension/background.js'
manifest_path = ROOT / 'extension/manifest.json'

bg = bg_path.read_text()
old = '''      .catch((err) => {
        sendResponse({ success: false, error: err.message });
      });
'''
new = '''      .catch((err) => {
        sendResponse({
          success: false,
          error: err.message || "Backup failed",
          code: err.code || "BACKUP_FAILED",
          details: err.details || null,
        });
      });
'''
if old not in bg:
    if 'code: err.code || "BACKUP_FAILED"' not in bg:
        raise SystemExit('backup error wrapper anchor missing')
else:
    bg = bg.replace(old, new, 1)

manifest = json.loads(manifest_path.read_text())
if manifest.get('version') not in ('1.0.64', '1.0.65'):
    raise SystemExit(f'unexpected manifest version: {manifest.get("version")}')
manifest['version'] = '1.0.65'

bg_path.write_text(bg)
manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
print('version_after=1.0.65')
print('backup_error_code_passthrough=', 'code: err.code || "BACKUP_FAILED"' in bg)
print('backup_error_details_passthrough=', 'details: err.details || null' in bg)
