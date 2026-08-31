#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path('/home/ubuntu/metashield-protocol')
i18n = ROOT / 'extension' / 'i18n.js'
manifest = ROOT / 'extension' / 'manifest.json'

if not i18n.is_file() or not manifest.is_file():
    raise SystemExit('metashield extension files not found')

s = i18n.read_text(encoding='utf-8')
zh = '''      "media.platformImagePost": "（圖片貼文）",\n      "media.platformVideoPost": "（影片貼文）",\n      "media.uploadFailed": "媒體上傳失敗",\n      "media.devnetQuota": "測試網媒體儲存額度不足或暫時不可用",\n      "media.imageUploadFailed": "圖片 {current}/{total} 上傳失敗：{detail}",\n      "media.noSuccessfulUpload": "圖片未能完整保存；本次備份已停止，避免產生不完整的成功紀錄。",\n'''
en = '''      "media.platformImagePost": "(image post)",\n      "media.platformVideoPost": "(video post)",\n      "media.uploadFailed": "Media upload failed",\n      "media.devnetQuota": "Devnet media storage quota is exhausted or temporarily unavailable",\n      "media.imageUploadFailed": "Image {current}/{total} upload failed: {detail}",\n      "media.noSuccessfulUpload": "Images were not fully preserved; this backup was stopped to avoid recording an incomplete success.",\n'''

if '"media.imageUploadFailed"' not in s:
    zmark = '      "backup.failed": "備份失敗",\n'
    emark = '      "backup.failed": "Backup failed",\n'
    if s.count(zmark) != 1 or s.count(emark) != 1:
        raise SystemExit('expected backup.failed markers not found uniquely')
    s = s.replace(zmark, zmark + zh, 1)
    s = s.replace(emark, emark + en, 1)
    i18n.write_text(s, encoding='utf-8')

m = json.loads(manifest.read_text(encoding='utf-8'))
before = str(m.get('version') or '')
if before not in {'1.0.60', '1.0.61'}:
    raise SystemExit(f'unexpected version: {before}')
if before == '1.0.60':
    m['version'] = '1.0.61'
    manifest.write_text(json.dumps(m, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

after = json.loads(manifest.read_text(encoding='utf-8'))['version']
if after != '1.0.61':
    raise SystemExit(f'failed version bump: {after}')
if '"media.imageUploadFailed"' not in i18n.read_text(encoding='utf-8'):
    raise SystemExit('missing media.imageUploadFailed after patch')

print(f'version_before={before}')
print(f'version_after={after}')
for line in i18n.read_text(encoding='utf-8').splitlines():
    if '"media.' in line:
        print(line.strip())
